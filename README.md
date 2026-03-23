# 🏠 Homelab Control System  
**Flask-based control panel + MQTT-driven remote control & status system**

---

## ⚠️ Disclaimer (Important)

This project allows **remote control of systems (shutdown, reboot, Wake-on-LAN, scripts, etc.)**.

❗ **Use at your own risk.**  
You are responsible for:
- system stability  
- data integrity  
- network security  
- access control  

Improper configuration can lead to:
- unintended shutdowns/reboots  
- data loss  
- unauthorized access  

---

# 📦 Project Overview

This setup consists of **two main parts**:

## 1️⃣ Homelab Panel (Web UI)
Runs on your main server (e.g. Raspberry Pi)

Provides:
- Web-based control panel (Flask)
- Wake-on-LAN buttons
- MQTT control buttons
- Local system control
- Live device status (Ping + MQTT)

---

## 2️⃣ Homelab Control (Remote Agent)
Runs on remote machines (e.g. Aoostar WTR, NAS, Proxmox nodes)

Provides:
- MQTT command listener
- System command execution
- Status reporting via MQTT
- Logging and state tracking

---

# 🧠 How It Works

[Web Panel] → MQTT → [Remote Device]  
[Remote Device] → MQTT → [Web Panel]

### Example: Shutdown flow

1. User clicks: "Sluk om 1 minut"
2. Panel sends:
   aoostar/control/power → shutdown_delay
3. Remote device executes script and publishes status:
   aoostar/status/action → shutdown_pending
   aoostar/status/last_command → shutdown -h +1
   aoostar/status/last_result → success
4. Panel updates UI

---

# 🖥️ Homelab Panel (Flask)

## Features

- 📡 Remote device status (Ping + MQTT)
- ⚡ Wake-on-LAN
- 🔌 MQTT control buttons
- 🖥️ Local system control (scripts)
- 🔄 Auto-refresh UI
- 🟢 Online only when BOTH Ping + MQTT are OK

---

# 🤖 Homelab Control (Remote Agent)

## Features

- Listens for MQTT commands
- Executes system scripts
- Publishes:
  - online/offline
  - current action
  - last command/result/message
- Stores state locally
- Logs all actions

---

# 🔧 Requirements

## Remote Device

sudo apt install python3-pip mosquitto-clients  
pip3 install paho-mqtt  

## Panel Server

pip3 install flask paho-mqtt  

---

# 🔍 Debugging

Check MQTT:

mosquitto_sub -h YOUR_BROKER -t 'aoostar/#' -v  

Check logs:

journalctl -u homelab-control-status-indicator.service  
journalctl -u homelab-control-command-listener.service  

---

# 🔐 Security Notes

- Use MQTT authentication  
- Restrict panel access  
- Do not expose publicly without protection  

---

# 🚀 Extending

Add new devices in devices.py — no HTML changes needed.

---

# 🎯 Final Note

This system gives you full control over your infrastructure.

⚠️ You are responsible for what happens when you press the buttons.

---

Enjoy your homelab 🚀
