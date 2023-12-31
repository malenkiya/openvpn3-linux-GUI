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

class MyApp:

    def __init__(self, root):

        self.root = root
        self.root.title("OpenVPN SAML")
        self.root.configure(bg="#222222")
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

        self.start_background_task()


    def toggle_autostart_desktop_file(self):
    
        home_dir = os.path.expanduser("~")
        autostart_dir = os.path.join(home_dir, ".config", "autostart")
        desktop_file_path = os.path.join(autostart_dir, "openvpn-saml.desktop")

        # Создаем директорию, если она не существует
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
            if self.update_tabs_flag:
                self.update_tabs(new_status=True)
            time.sleep(1)
            if  self.autoconnect_finished == False:
                self.autostart_connections()
                

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
                version = tk.Label(root, text="v.0.2", bg="#222222", fg="white", font=("Arial", 8, "bold"))
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
            self.update_output(str(e))

        return active_sessions
        

    def get_all_sessions(self):
        active_sessions = []
        sessions_manager_object = self.bus.get_object('net.openvpn.v3.sessions', '/net/openvpn/v3/sessions')
        sessions_manager_interface = dbus.Interface(sessions_manager_object, dbus_interface='net.openvpn.v3.sessions')
        try:
            session_paths = sessions_manager_interface.FetchAvailableSessions()
            active_sessions = [self.extract_session_name(session_path) for session_path in session_paths]
        except dbus.exceptions.DBusException as e:
            self.update_output(str(e))

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

        self.update_output("Trying to connect via created tunnel..")
        new_connect = sessions_manager_interface.Connect()

        ready_timer = 0
        while True:
            ready_timer = ready_timer + 0.3
            time.sleep(0.3)
            auth_url = self.get_web_link(new_tunnel)
            if ready_timer >= 5:
                break
            elif "http" in auth_url:
                break
        webbrowser.open(auth_url)


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
    root = tk.Tk(className='OpenVPN SAML')
    app = MyApp(root)
    root.mainloop()

