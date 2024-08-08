import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, PhotoImage
import dbus
import time
import webbrowser
import subprocess
import threading
import datetime
import json
import os
import shutil
import signal
import sys
import psutil
import socket
import pickle

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtGui import QIcon
from multiprocessing import Process, set_start_method, freeze_support




os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

class Browser(QMainWindow):
    def __init__(self, urls, title):
        super().__init__()
        self.urls = urls
        self.initUI(title)

    def initUI(self, title):
        profile_path = os.path.expanduser("~/.config/pyqt_browser_profile")
        self.profile = QWebEngineProfile(profile_path, self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        for url in self.urls:
            self.add_tab(url)

        self.resize(390, 800)
        self.setWindowTitle(title)
        self.show()

    def add_tab(self, url):
        browser = QWebEngineView()
        page = QWebEnginePage(self.profile, browser)
        browser.setPage(page)

        settings = browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

        browser.setUrl(QUrl(url))
        page.windowCloseRequested.connect(self.handleWindowCloseRequested)

        # Check for 'window.close()' in the page source after it has loaded
        page.loadFinished.connect(lambda: self.check_page_for_window_close(page, browser))

        tab_index = self.tab_widget.addTab(browser, QUrl(url).host())
        self.tab_widget.setCurrentIndex(tab_index)

    def check_page_for_window_close(self, page, browser):
        # Get the page source and check for 'window.close()'
        page.runJavaScript("document.documentElement.outerHTML", lambda source: self.handle_page_source(source, browser))

    def handle_page_source(self, source, browser):
        if source is None:
            print("Failed to retrieve page source")
        elif 'window.close()' in source:
            print("Found window.close() in page source")
            # Close the tab after 3 seconds
            QTimer.singleShot(3000, lambda: self.close_tab(browser))

    def close_tab(self, browser):
        if browser:
            index = self.tab_widget.indexOf(browser)
            if index != -1:
                self.tab_widget.removeTab(index)
                browser.page().deleteLater()
                browser.deleteLater()

        if self.tab_widget.count() == 0:
            self.close()

    def handleWindowCloseRequested(self):
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            page = current_widget.page()
            page.deleteLater()
            current_widget.deleteLater()
            self.tab_widget.removeTab(self.tab_widget.currentIndex())
        if self.tab_widget.count() == 0:
            self.close()

    def closeEvent(self, event):
        while self.tab_widget.count() > 0:
            current_widget = self.tab_widget.widget(0)
            if current_widget:
                page = current_widget.page()
                page.deleteLater()
                current_widget.deleteLater()
                self.tab_widget.removeTab(0)
        event.accept()

def start_browser(urls):
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    icon = QIcon("/opt/openvpn-saml/openvpn.png")
    app.setWindowIcon(icon)
    app.setApplicationName("OpenVPN SAML AUTH")
    window = Browser(urls, "OpenVPN SAML AUTH")
    window.show()
    app.exec()

def run_browser_in_process(urls):
    process = Process(target=start_browser, args=(urls,))
    process.name = "OPENVPN SAML AUTH browser"
    process.start()
    #process.join()
    return process.pid





class MyApp:

    def __init__(self, root):

        self.root = root
        self.root.title("OpenVPN SAML")
        self.root.configure(bg="#222222")
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
        self.root.geometry("600x280")
        self.root.resizable(False, False)
        style = ttk.Style(root)
        img = PhotoImage(file='/opt/openvpn-saml/openvpn.png')
        self.root.iconphoto(False, img)
        self.menu_bar = tk.Menu(root, bg="#222222", fg="white", activebackground="#454545", activeforeground="white")
        root.config(menu=self.menu_bar)
        self.auto_restart_settings = self.load_auto_restart_settings()
        self.config_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#222222", fg="white", activebackground="#454545", activeforeground="white")
        self.menu_bar.add_cascade(label="Config", menu=self.config_menu)
        self.config_menu.add_command(label="Add config", command=self.add_config)
        self.config_menu.add_command(label="Remove config", command=self.remove_config)
        self.bus = dbus.SystemBus()

        self.sessions_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#222222", fg="white", activebackground="#454545", activeforeground="white")
        self.menu_bar.add_cascade(label="Sessions", menu=self.sessions_menu)
        self.sessions_menu.add_command(label="Kill all sessions", command=self.kill_sessions)

        self.settings_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#222222", fg="white", activebackground="#454545", activeforeground="white")
        self.menu_bar.add_cascade(label="Settings", menu=self.settings_menu)
        self.settings_menu.add_command(label="Start program on boot (toggle)", command=self.toggle_autostart_desktop_file)

        self.output_text = tk.Text(root, wrap="word", height=10, width=80, bg="black", fg="orange", bd=0)
        self.output_text.pack(side='top', fill='both', expand=True, padx=10, pady=10)
        self.output_text.columnconfigure(0, weight=1)
        self.output_text.configure(state='disabled')

        self.notebook = ttk.Notebook(root, style='Dark.TNotebook')
        self.notebook.pack(side='bottom', fill='both', expand=True)
        self.notebook.pack_propagate(False)
        style = ttk.Style()
        style.configure('Dark.TNotebook', background='#222222')

        self.config_names = set()
        self.button_state_vars = {}

        self.background_task_lock = threading.Lock()
        self.button_lock = threading.Lock()
        self.update_tabs_flag = True
        self.command_executing = False
        self.autoconnect_finished = False
        self.auth_urls = []
        self.browser_is_running = False
        self.vpn_status_list = []
        self.start_background_task()
        self.root.withdraw()

        self.start_unix_socket_listener('/opt/openvpn-saml/openvpn-saml-backend.socket')


        self.check_thread = threading.Thread(target=self._check_auth_urls)
        self.check_thread.daemon = True  
        self.check_thread.start()

    def _check_auth_urls(self):
        wait_time = 0
        while True:
            time.sleep(1)
            if len(self.auth_urls) >= 3:
                urls_to_process = self.auth_urls[:]
                self.auth_urls = []
                self.update_output("3 web links ready, connecting")
                run_browser_in_process([url for auth_dict in urls_to_process for url in auth_dict.values()])
                wait_time = 0  # Reset the wait time after processing
            elif self.auth_urls:
                wait_time += 1
                if wait_time >= 10:
                    self.update_output("10 seconds to collect urls passed, connecting ")
                    urls_to_process = self.auth_urls[:]
                    self.auth_urls = []
                    run_browser_in_process([url for auth_dict in urls_to_process for url in auth_dict.values()])
                    wait_time = 0  # Reset the wait time after processing
            else:
                wait_time = 0  # Reset the wait time if no URLs are present

    def start_unix_socket_listener(self, socket_path):
        self.socket_thread = threading.Thread(target=self.listen_unix_socket, args=(socket_path,), daemon=True)
        self.socket_thread.start()

    def listen_unix_socket(self, socket_path):
        if os.path.exists(socket_path):
            os.remove(socket_path)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_socket:
            server_socket.bind(socket_path)
            server_socket.listen()
            print(f"Listening on UNIX socket {socket_path}")

            while True:
                conn, _ = server_socket.accept()
                with conn:
                    data = conn.recv(1024)
                    if not data:
                        break
                    command = pickle.loads(data)
                    func_name = command.get('function')
                    args = command.get('args', {})
                    try:
                        if func_name == "open_settings":
                            self.restore_window()
                            response = {'status': 'success', 'result': 'Settings opened'}
                        elif func_name == "quit":
                            self.kill_sessions()
                            self.root.quit()
                            response = {'status': 'success', 'result': 'Tray app commanded to exit'}
                        elif func_name == "ping":
                            response = {'status': 'success', 'result': 'Pong'}
                        elif func_name == "get_vpn_status":
                            response = self.vpn_status_list
                        elif func_name == "connect":
                            configs = self.get_available_config_names()
                            config_name = args.get('config')
                            active_sessions = self.get_sessions_for_config(config_name)
                            self.disconnect_sessions(active_sessions)
                            print(f"Tray app request to connect config {config_name}")
                            button_state_var = self.button_state_vars[config_name]
                            config_path = self.find_config_path_by_name(config_name)
                            response = {'status': 'success', 'result': 'ok'}
                            self.toggle_vpn(config_path, button_state_var)
                        elif func_name == "restart_all_connections":
                            self.kill_sessions()
                            configs = self.get_available_config_names()
                            for config_name in configs:
                                for key, value in config_name.items():
                                    button_state_var = self.button_state_vars[value]
                                    config_path = self.find_config_path_by_name(value)
                                    self.toggle_vpn(config_path, button_state_var)
                                    time.sleep(1)
                            response = {'status': 'success', 'result': f'All sessions restarted'}

                        elif func_name == "stop_all_connections":
                            self.kill_sessions()
                            response = {'status': 'success', 'result': f'All sessions stopped'}

                        elif func_name in globals():
                            result = globals()[func_name]()
                            response = {'status': 'success', 'result': result}
                        else:
                            response = {'status': 'error', 'message': f"Function {func_name} not found"}

                        conn.sendall(pickle.dumps(response))
                    except Exception as e:
                        response = {'status': 'error', 'message': f'Exception on backend: {e}', 'exception': e}
                        conn.sendall(pickle.dumps(response))
 
    def minimize_to_tray(self):
        self.root.withdraw()

    def restore_window(self):
        self.root.withdraw()
        self.root.deiconify()
   
    def toggle_autostart_desktop_file(self):
    
        home_dir = os.path.expanduser("~")
        autostart_dir = os.path.join(home_dir, ".config", "autostart")
        desktop_file_path = os.path.join(autostart_dir, "openvpn-saml.desktop")

        os.makedirs(autostart_dir, exist_ok=True)

        if os.path.exists(desktop_file_path):
            try:
                os.remove(desktop_file_path)
                self.update_output(f"Removed desktop file {desktop_file_path}.")
            except OSError as e:
                self.update_output(f"Error removing desktop file: {e}.")
        else:
            try:
                shutil.copy("/opt/openvpn-saml/openvpn-saml.desktop", desktop_file_path)
                self.update_output(f"Added desktop file to {desktop_file_path}.")
            except FileNotFoundError:
                self.update_output(f"Error: The desktop file to be added was not found.")
            except shutil.Error as e:
                self.update_output(f"Error adding desktop file: {e}.")


    def save_auto_restart_setting(self, config_name, auto_restart_value, dco_value):

        config_file_path = '/opt/openvpn-saml/auto_restart_settings.json'

        if config_name not in self.auto_restart_settings:
            self.auto_restart_settings[config_name] = {}

        self.auto_restart_settings[config_name]['auto_restart'] = auto_restart_value
        self.update_output(f"{config_name}: auto_restart_value:{auto_restart_value}")
        self.auto_restart_settings[config_name]['dco'] = dco_value

        with open(config_file_path, "w", encoding="utf-8") as config_file:
            json.dump(self.auto_restart_settings, config_file, ensure_ascii=False)

        config_path = self.find_config_path_by_name(config_name)
        if dco_value:
            self.set_configuration_properties(config_path,"dco",True)
        else:
            self.set_configuration_properties(config_path,"dco",False)
        dco_status = self.get_configuration_properties(config_path,"dco")
        self.update_output(f"{config_name}: {str(dco_status)}")
        

    def load_auto_restart_settings(self):

        config_file_path = '/opt/openvpn-saml/auto_restart_settings.json'
        try:
            with open(config_file_path, "r", encoding="utf-8") as config_file:
                return json.load(config_file)
        except FileNotFoundError:
            return {}


    def start_background_task(self):

        self.background_thread = threading.Thread(target=self.update_status_label)
        self.background_thread.daemon = True
        self.update_tabs()
        self.background_thread.start()
        

    def autostart_connections(self):

        configs = self.get_available_config_names()
        if self.autoconnect_finished == False:
            check_openvpn3 = subprocess.run("openvpn3 sessions-list", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "CompletedProcess" in str(check_openvpn3):
                self.update_output("openvpn3 client found, OK.")
            else:
                self.update_output("openvpn3 client not found, program may not work.")
            if configs == []:
                self.update_output("No configs found. Please add new config.")
            for config in configs:
                config_name = list(config.values())[0]
                config_path = list(config.keys())[0]
                auto_restart_var = tk.BooleanVar(value=self.auto_restart_settings.get(config_name, {}).get('auto_restart', False)).get()
                if auto_restart_var == True:
                    active_sessions = self.get_sessions_for_config(config_name)
                    if active_sessions == []:
                        self.update_output(f"Starting autoconnect for {config_name}...")
                        self.connect_session(config_path)
                        toggle_button = self.get_toggle_button(config_name)
                        button_state_var = self.button_state_vars[config_name]
                        button_state_var.set("Disconnect")
                        toggle_button.config(bg="red")
                    else:
                        self.update_output(f"Active sessions found for {config_name}. Not autoconnecting.")
                else:
                    active_sessions = self.get_sessions_for_config(config_name)
                    if active_sessions == []:
                        self.update_output(f"Config {config_name} has no active sessions.")
                    else:
                        self.update_output(f"Active sessions found for {config_name}.")

            self.autoconnect_finished = True
            

    def update_status_label(self):

        while True:
            try:
                if self.update_tabs_flag:
                    self.update_tabs(new_status=True)
                time.sleep(1)
                if  self.autoconnect_finished == False:
                    self.autostart_connections()
            except Exception as e:
                self.update_output(f"Exception on update_status_label: {e}")

    def update_status_list(self, config_name, status):
        found = False
        for i, entry in enumerate(self.vpn_status_list):
            if entry.startswith(config_name + ":"):
                self.vpn_status_list[i] = f"{config_name}:{status}"
                found = True
                break
        
        if not found:
            self.vpn_status_list.append(f"{config_name}:{status}")                

    def add_config(self):

        self.update_tabs_flag = False
        file_path = filedialog.askopenfilename(title="Choose a configuration file")
        self.update_tabs_flag = True
        if file_path:
            config_name = simpledialog.askstring("Configuration Name", "Enter a name for the new configuration")
            if config_name and config_name not in self.config_names:
                output_message = f"Selected file: {file_path}\nAdded config: {config_name}"
                self.update_output(output_message)

                with open(file_path, 'r') as file:
                    config_content = file.read()

                config_path = self.import_configuration(config_name, config_content)
                output_message = f"Added config: {config_path}"
                self.update_output(output_message)

                self.config_names.add(config_name)
                self.update_tabs()
                self.update_tabs(new_status=True)
            elif config_name:
                output_message = f"Configuration with the name '{config_name}' already exists."
                self.update_output(output_message)
            else:
                print("Cancelled by the user.")
                

    def remove_config(self):

        selected_tab_index = self.notebook.index(self.notebook.select())
        selected_tab_name = self.notebook.tab(selected_tab_index, option="text")
        if selected_tab_name:
            config_path = self.find_config_path_by_name(selected_tab_name)
            if config_path:
                self.remove_configuration(config_path)
                output_message = f"Removed config: {selected_tab_name}."
                self.update_output(output_message)
                self.config_names.remove(selected_tab_name)
                self.update_tabs()
                self.update_tabs(new_status=True)
            else:
                output_message = f"Configuration with the name '{selected_tab_name}' not found."
                self.update_output(output_message)
        else:
            self.update_output("No configuration selected to remove.")
           
        self.update_tabs_flag = True
        

    def update_tabs(self, new_status=False):

        if new_status == False:
            for tab_id in self.notebook.tabs():
                self.notebook.forget(tab_id)
            try:
                configs = self.get_available_config_names()
            except dbus.exceptions.DBusException:
                self.update_output("No such interface net.openvpn.v3.configuration. Trying to add one.")
                configs = self.get_available_config_names()
            for config in configs:
                config_path, config_name = list(config.items())[0]
                tab_frame = tk.Frame(self.notebook, bg="#6c6c6c")

                active_sessions = self.get_sessions_for_config(config_name)
                button_text = "Disconnect" if active_sessions else "Connect"

                button_state_var = tk.StringVar(value=button_text)

                toggle_button = tk.Button(
                    tab_frame,
                    textvariable=button_state_var,
                    command=lambda c=config_path, b=button_state_var: self.toggle_vpn(c, b),
                    bg="red" if active_sessions else "green",
                    fg="white",
                    font=("Arial", 10, "bold"),
                    width=8
                )
                toggle_button.pack(side='right', padx=10)

                self.button_state_vars[config_name] = button_state_var

                label1 = tk.Label(tab_frame, text=new_status, bg="#222222", fg="white", font=("Arial", 10, "bold"))
                label1.pack(pady=(13, 0), padx=(410, 0))
                version = tk.Label(root, text="v.0.3", bg="#222222", fg="white", font=("Arial", 8, "bold"))
                version.place(x=560, y=258)

                auto_restart_var = tk.BooleanVar(value=self.auto_restart_settings.get(config_name, {}).get('auto_restart', False))
                dco_var = tk.BooleanVar(value=self.auto_restart_settings.get(config_name, {}).get('dco', False))

                dco_checkbox = tk.Checkbutton(tab_frame, text="DCO", variable=dco_var, selectcolor="#222222", bg="#222222", fg="white", font=("Arial", 11, "bold"), bd=0, highlightthickness=0,
                               command=lambda name=config_name, var=dco_var, auto_restart_var=auto_restart_var: self.save_auto_restart_setting(name, auto_restart_var.get(), var.get()))
                dco_checkbox.place(x=128, y=13)
                auto_restart_checkbox = tk.Checkbutton(tab_frame, text="Autoconnect", variable=auto_restart_var, selectcolor="#222222", bg="#222222", fg="white", font=("Arial", 11, "bold"), bd=0, highlightthickness=0,
                               command=lambda name=config_name, var=auto_restart_var, dco_var=dco_var: self.save_auto_restart_setting(name, var.get(), dco_var.get()))
                auto_restart_checkbox.place(x=8, y=13)
                self.notebook.add(tab_frame, text=config_name)
                

        if new_status == True:

            for tab_id in self.notebook.tabs():
                status = ""
                config_name = self.notebook.tab(tab_id, "text")
                active_sessions = self.get_sessions_for_config(config_name)
                if active_sessions != []:
                    try:
                        status = self.get_session_status(f'/net/openvpn/v3/sessions/{active_sessions[0]}')
                    except:
                        pass
                    if "Connected" in status:
                        status = "VPN Online"
                        color = "green"
                        config_path = self.find_config_path_by_name(config_name)
                    elif "Starting" in status:
                        status = "Starting..."
                        color = "orange"
                    elif "Connecting" in status:
                        status = "Connecting..."
                        color = "orange"
                    else:
                        color = "orange"
                else:
                    status = "VPN Offline"
                    color = "red"
                self.update_status_list(config_name, status)

                tab_frame = self.notebook.nametowidget(tab_id)
                tab_frame.configure(bg="#222222")

                label1 = tab_frame.winfo_children()[1]

                if status != "":
                    label1.config(text=status, fg=color, bg="#222222")
                    style = ttk.Style()
                    style.configure("TNotebook", background="#222222", tabposition='sw')
                    style.map("TNotebook.Tab", background=[("selected", "#ed9121"), ("!selected", "#454545")], foreground=[("selected", "white"), ("!selected", "white")])
                    style.configure("TNotebook.Tab", font=("Arial", 12, "bold"))


    def lock_unlock_button(self, config_name, lock):
        toggle_button = self.get_toggle_button(config_name)
        if lock:
            toggle_button["state"] = "disabled"
        else:
            toggle_button["state"] = "normal"

    def update_output(self, message):

        message = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + ' ' + message + '\n'
        self.output_text.configure(state='normal')
        self.output_text.insert('end', message)
        self.output_text.configure(state='disabled')
        self.output_text.see('end')
        self.root.update()
        

    def toggle_vpn(self, config_path, button_state_var):
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                current_state = button_state_var.get()
                config_name = self.get_configuration_properties(config_path, "name")['name']
                active_sessions = self.get_sessions_for_config(config_name)

                if current_state == "Connect":
                    if not self.command_executing:
                        with self.button_lock:
                            self.lock_unlock_button(config_name, True)  # Lock the button
                            self.command_executing = True
                            if active_sessions:
                                self.disconnect_sessions(active_sessions)
                                self.connect_session(config_path)
                            else:
                                self.connect_session(config_path)
                            toggle_button = self.get_toggle_button(config_name)
                            toggle_button.config(bg="red")
                            button_state_var.set("Disconnect")
                            self.command_executing = False
                            self.lock_unlock_button(config_name, False)  # Unlock the button

                elif current_state == "Disconnect":
                    if not self.command_executing:
                        with self.button_lock:
                            self.lock_unlock_button(config_name, True)  # Lock the button
                            self.command_executing = True
                            if active_sessions:
                                self.disconnect_sessions(active_sessions)
                            toggle_button = self.get_toggle_button(config_name)
                            toggle_button.config(bg="green")
                            button_state_var.set("Connect")
                            self.command_executing = False
                            self.lock_unlock_button(config_name, False)  # Unlock the button
                
                break  # If successful, exit the loop
            except Exception as e:
                print(f"exception on toggle_vpn func: {e}")
                if "org.freedesktop.DBus.Error.UnknownMethod" in str(e):
                    time.sleep(1)
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"Retrying ({retry_count}/{max_retries})...")
                    else:
                        print("Max retries reached. Giving up.")
                        break
                else:
                    break  # If a different exception occurs, do not retry


    def get_toggle_button(self, config_name):

        tabs = self.notebook.tabs()
        for tab_id in tabs:
            tab_name = self.notebook.tab(tab_id, option="text")
            if tab_name == config_name:
                tab_frame = self.notebook.nametowidget(tab_id)
                toggle_button = tab_frame.winfo_children()[0]
                return toggle_button
                

    def kill_sessions(self):

        active_sessions = self.get_all_sessions()
        if active_sessions:
            self.disconnect_sessions(active_sessions)
            output_message = f"Killed all sessions: {', '.join(active_sessions)}"
            self.update_output(output_message)

            for config_name in self.config_names:
                active_sessions = self.get_sessions_for_config(config_name)
                toggle_button = self.get_toggle_button(config_name)

                if not active_sessions:
                    button_state_var = self.button_state_vars[config_name]
                    button_state_var.set("Connect")
                    toggle_button.config(bg="green")

        else:
            output_message = "No active sessions to kill."
            self.update_output(output_message)
        self.update_tabs_flag = True
        

    def import_configuration(self, config_name, config_content):

        manager_object = self.bus.get_object('net.openvpn.v3.configuration', '/net/openvpn/v3/configuration')
        config_interface = dbus.Interface(manager_object, dbus_interface='net.openvpn.v3.configuration')
        config_path = config_interface.Import(config_name, config_content, False, True)
        return config_path

    def find_config_path_by_name(self, config_name):

        config_manager_object = self.bus.get_object('net.openvpn.v3.configuration', '/net/openvpn/v3/configuration')
        config_manager_interface = dbus.Interface(config_manager_object, dbus_interface='net.openvpn.v3.configuration')
        config_paths = config_manager_interface.FetchAvailableConfigs()

        for config_path in config_paths:
            properties = self.get_configuration_properties(config_path,"name")
            if properties['name'] == config_name:
                return config_path
        return None
        

    def remove_configuration(self, config_path):

        config_object = self.bus.get_object('net.openvpn.v3.configuration', config_path)
        config_interface = dbus.Interface(config_object, dbus_interface='net.openvpn.v3.configuration')
        config_interface.Remove()
        

    def get_configuration_properties(self, config_path,property_name):

        config_object = self.bus.get_object('net.openvpn.v3.configuration', config_path)
        properties_interface = dbus.Interface(config_object, dbus_interface='org.freedesktop.DBus.Properties')
        interface_name = 'net.openvpn.v3.configuration'
        property_value = properties_interface.Get(interface_name, property_name)
        return {
            property_name: property_value,
        }
        

    def set_configuration_properties(self, config_path,property_name,property_value):

        config_object = self.bus.get_object('net.openvpn.v3.configuration', config_path)
        properties_interface = dbus.Interface(config_object, dbus_interface='org.freedesktop.DBus.Properties')
        interface_name = 'net.openvpn.v3.configuration'
        property_value = properties_interface.Set(interface_name, property_name, property_value)
        return {
            property_name: property_value,
        }
        

    def get_available_config_names(self):

        configs = []
        config_manager_object = self.bus.get_object('net.openvpn.v3.configuration', '/net/openvpn/v3/configuration')
        config_manager_interface = dbus.Interface(config_manager_object, dbus_interface='net.openvpn.v3.configuration')
        config_paths = config_manager_interface.FetchAvailableConfigs()

        self.output_text.configure(state='normal')
        self.output_text.delete(1.0, 'end')
        self.output_text.configure(state='disabled')

        for config_path in config_paths:
            config_name = self.get_configuration_properties(config_path,"name")['name']
            configs.append({str(config_path): str(config_name)})
            self.config_names.add(config_name)

        return configs
        

    def get_sessions_for_config(self, config_name):

        active_sessions = []
        sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', '/net/openvpn/v3/sessions')
        sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')
        try:
            session_paths = sessions_manager_interface.LookupConfigName(config_name)
            active_sessions = [self.extract_session_name(session_path) for session_path in session_paths]
        except dbus.exceptions.DBusException as e:
            self.update_output(f'Exeption on func get_sessions_for_configs:  {str(e)}')

        return active_sessions
        

    def get_all_sessions(self):
        active_sessions = []
        sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', '/net/openvpn/v3/sessions')
        sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')
        try:
            session_paths = sessions_manager_interface.FetchAvailableSessions()
            active_sessions = [self.extract_session_name(session_path) for session_path in session_paths]
        except dbus.exceptions.DBusException as e:
            self.update_output(f'Exeption on func get_all_sessions:  {str(e)}')

        return active_sessions
        

    def disconnect_sessions(self, session_paths):

        for session in session_paths:
            self.update_output(f"Session {session} is killed.")
            sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', f'/net/openvpn/v3/sessions/{session}')
            sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')
            sessions_manager_interface.Disconnect()
            

    def connect_session(self, config_path):


        sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', f'/net/openvpn/v3/sessions')
        sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')
        new_tunnel = sessions_manager_interface.NewTunnel(config_path)
        self.update_output(f"Creating new tunnel and check if it's ready for {config_path}")
        sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', new_tunnel)
        sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')


        ready_timer = 0
        while True:
            try:
                ready_timer = ready_timer + 1
                self.update_output(f"Starting tunnel..Waiting for Ready state {ready_timer} sec..")
                time.sleep(1)
                is_ready = sessions_manager_interface.Ready()
                if is_ready is None:
                    self.update_output(f"Tunnel for {config_path} is ready.")
                    break
                elif ready_timer >= 10:
                    self.update_output("Tunnel failed to start during 10 sec. Aborting..")
                    break
            except dbus.exceptions.DBusException as e:
                error_message = str(e)
                self.update_output(f"DBusException: {error_message}")
                break

        self.update_output("Trying to connect via created tunnel..")
        new_connect = sessions_manager_interface.Connect()

        ready_timer = 0
        while True:
            try:
                ready_timer = ready_timer + 0.3
                time.sleep(0.3)
                auth_url = self.get_web_link(new_tunnel)
                if ready_timer >= 5:
                    break
                if "http" in auth_url:
                    self.auth_urls.append({str(config_path):auth_url})
                    break
            except Exception as e:
                break
                print(f"Exception on func connect_session {e}")


    def extract_session_name(self, session_path):

        return session_path.split('/')[-1]
        

    def get_web_link(self, session_path):

        config_object = self.bus.get_object('net.openvpn.v3.sessions', session_path)
        properties_interface = dbus.Interface(config_object, dbus_interface='org.freedesktop.DBus.Properties')
        interface_name = 'net.openvpn.v3.sessions'
        property_name = 'status'
        property_value = properties_interface.Get(interface_name, property_name)
        web_link = str(property_value[2])
        self.update_output(f'Auth link: {web_link}')
        return web_link
        

    def get_session_status(self, session_path):

        config_object = self.bus.get_object('net.openvpn.v3.sessions', session_path)
        properties_interface = dbus.Interface(config_object, dbus_interface='org.freedesktop.DBus.Properties')
        interface_name = 'net.openvpn.v3.sessions'
        property_values = properties_interface.GetAll(interface_name)
        try:
            session_status = property_values[dbus.String('last_log')][dbus.String('log_message')]
        except KeyError:
            pass
        return session_status


if __name__ == "__main__":
    freeze_support()
    root = tk.Tk(className='OpenVPN SAML')
    app = MyApp(root)
    root.mainloop()
