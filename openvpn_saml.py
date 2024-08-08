from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer
import socket
import pickle
import sys
import signal
import time
import subprocess

STATUS_ICONS = {
    'green': '/opt/openvpn-saml/green.png',
    'yellow': '/opt/openvpn-saml/yellow.png',
    'red': '/opt/openvpn-saml/red.png',
}

last_statuses = {}
status_timestamps = {}
actions = {}  # Store actions for access

first_run = True
is_starting = False
start_timer = 0

def kill_processes_by_path(path):
    """Forcefully kill all processes with the given executable path using pkill."""
    try:
        # Extract the executable name from the path
        executable_name = path.split('/')[-1]
        print(f"Killing processes with executable name {executable_name}...")
#        subprocess.run(['pkill', '-f', executable_name], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error killing processes: {e}")

def send_unix_command(function_name, args=None, socket_path='/opt/openvpn-saml/openvpn-saml-backend.socket'):
    global is_starting
    global start_timer
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(socket_path)
            command = {'function': function_name, 'args': args}
            s.sendall(pickle.dumps(command))
            data = s.recv(1024)
            response = pickle.loads(data)
            print('Received response:', response)
            is_starting = False
            return response
    except socket.error as e:
        if e.errno == 111 or e.errno == 2:  # Connection refused
            if not is_starting:
                print("Connection refused. Terminating existing OpenVPN GUI backend processes...")
                print("Starting the OpenVPN GUI backend...")
                is_starting = True
                kill_processes_by_path('/opt/openvpn-saml/openvpn-saml-backend')
                process = subprocess.Popen(['/opt/openvpn-saml/openvpn-saml-backend'])
                print(f"Started process: {process.pid}")
            else:
                if start_timer <= 30:
                    start_timer += 1
                else:
                    kill_processes_by_path('/opt/openvpn-saml/openvpn-saml-backend')
                    start_timer = 0 

        else:
            print(f"Socket error: {e}")
    except Exception as e:
        print(f"Error sending command: {e}")
    return None

def load_status_icon(color):
    try:
        icon_path = STATUS_ICONS.get(color, STATUS_ICONS['red'])
        return QIcon(icon_path)
    except Exception as e:
        print(f"Error loading icon {icon_path}: {e}")
        return QIcon()

def update_tray_icon():
    global last_statuses
    global first_run
    try:
        if not last_statuses:
            tray_icon.setIcon(load_status_icon('red'))
        else:
            any_connecting = any("Starting" in status or "Connecting" in status for status in last_statuses.values())
            any_online = any("Online" in status for status in last_statuses.values())

            if any_connecting:
                tray_icon.setIcon(load_status_icon('yellow'))
            elif any_online:
                tray_icon.setIcon(load_status_icon('green'))
                first_run = False
            else:
                tray_icon.setIcon(load_status_icon('red'))
    except Exception as e:
        print(f"Error updating tray icon: {e}")

def disable_actions_for_seconds(actions_list, seconds):
    """Disable a list of actions for a specified number of seconds."""
    for action in actions_list:
        action.setEnabled(False)
    QTimer.singleShot(seconds * 1000, lambda: [action.setEnabled(True) for action in actions_list])

def handle_restart_stop_action(action, command):
    """Handles the 'Restart all' and 'Stop all' actions, disabling both actions for 15 seconds."""
    try:
        global first_run
        first_run = True
        # Disable both actions
        disable_actions_for_seconds([actions['restart'], actions['stop']], 15)
        send_unix_command(command)
    except Exception as e:
        print(f"Error handling restart/stop action: {e}")

def handle_config_click(action, config_name):
    try:
        global first_run
        print(f"Configuration {config_name} clicked")
        first_run = True
        action.setEnabled(False)

        QTimer.singleShot(3000, lambda: action.setEnabled(True))

        response = send_unix_command('connect', args={'config': config_name})
        if "DBusException" in response:
            send_unix_command('connect', args={'config': config_name})

        for menu_action in tray_icon.contextMenu().actions():
            if menu_action.text() == config_name:
                menu_action.setIcon(load_status_icon('yellow'))
                break
    except Exception as e:
        print(f"Error handling config click for {config_name}: {e}")

def update_menu(menu):
    global last_statuses, status_timestamps, actions
    try:
        statuses = send_unix_command('get_vpn_status')

        if statuses:
            new_statuses = {s.split(':')[0]: s.split(':')[1] for s in statuses}
            current_time = time.time()

            if new_statuses != last_statuses:
                last_statuses = new_statuses
                status_timestamps = {config: current_time for config in new_statuses}

                menu.clear()

                for config, status in new_statuses.items():
                    color = 'red'
                    if "Online" in status:
                        color = 'green'
                    elif "Starting" in status or "Connecting" in status or "Reconnecting" in status:
                        color = 'yellow'

                    config_action = QAction(load_status_icon(color), config, app)
                    config_action.triggered.connect(lambda _, cfg=config, act=config_action: handle_config_click(act, cfg))
                    menu.addAction(config_action)

                    status_action = QAction(status, app)
                    status_action.setEnabled(False)
                    menu.addAction(status_action)
                    menu.addSeparator()
            else:
                return
        else:
            menu.clear()
            if is_starting:
                error_action = QAction('Backend starting....', app)
            else:
                error_action = QAction('Error fetching VPN statuses', app)
            last_statuses = {'Error.': 'Error connecting to backend, try to restart app.'}
            error_action.setEnabled(False)
            menu.addAction(error_action)
            menu.addSeparator()

        # Create and store actions for restart and stop
        restart_action = QAction("Restart all", app)
        actions['restart'] = restart_action
        restart_action.triggered.connect(lambda: handle_restart_stop_action(restart_action, 'restart_all_connections'))
        menu.addAction(restart_action)

        stop_action = QAction("Stop all", app)
        actions['stop'] = stop_action
        stop_action.triggered.connect(lambda: handle_restart_stop_action(stop_action, 'stop_all_connections'))
        menu.addAction(stop_action)
        menu.addSeparator()

        settings_action = QAction('Settings', app)
        settings_action.triggered.connect(lambda: send_unix_command('open_settings'))
        menu.addAction(settings_action)

        quit_action = QAction('Quit', app)
        quit_action.triggered.connect(lambda: send_unix_command('quit'))
        quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)

        update_tray_icon()
    except Exception as e:
        print(f"Error updating menu: {e}")

def check_statuses():
    global last_statuses, status_timestamps, first_run
    current_time = time.time()
    for config, status in last_statuses.items():
        if any(status.startswith(prefix) for prefix in ("Reconnecting", "Connecting", "Starting")):
            if current_time - status_timestamps.get(config, current_time) > 60 and first_run == False:
                print(f"Status {status} for {config} persisted for more than 60 seconds. Triggering connect.")
                send_unix_command('connect', args={'config': config})
                send_unix_command('connect', args={'config': config})
                status_timestamps[config] = current_time

class CustomMenu(QMenu):
    def showEvent(self, event):
        try:
            update_menu(self)
        except Exception as e:
            print(f"Error showing menu: {e}")
        super().showEvent(event)

try:
    app = QApplication(sys.argv)

    tray_icon = QSystemTrayIcon(QIcon('/opt/openvpn-saml/openvpn.png'))
    tray_icon.setToolTip("Tray Icon")

    tray_icon.setContextMenu(CustomMenu())
    tray_icon.show()

    menu_timer = QTimer()
    menu_timer.timeout.connect(lambda: update_menu(tray_icon.contextMenu()))
    menu_timer.start(2000)

    status_timer = QTimer()
    status_timer.timeout.connect(check_statuses)
    status_timer.start(1000)

    def signal_handler(sig, frame):
        tray_icon.hide()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    sys.exit(app.exec())
except Exception as e:
    print(f"Error initializing application: {e}")
