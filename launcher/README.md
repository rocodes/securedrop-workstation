# securedrop-workstation updater

The Updater ensures that the SecureDrop Workstation is up-to-date by checking for and applying any necessary VM updates, which may prompt a reboot.

## Running the Updater

Qubes 4.0.3 uses an end-of-life Fedora template in dom0 (fedora-25). See rationale here: https://www.qubes-os.org/doc/supported-versions/#note-on-dom0-and-eol.

To run the preflight updater:
1. Open a `dom0` terminal
2. Run `/opt/securedrop/launcher/sdw-udpater.py --skip-delta 0`

To run the notifier that pops up if `/proc/uptime` (how long the system has been on since its last restart) is greater than 30 seconds and `~/.securedrop_launcher/sdw-last-updated` (how long it's been since the Updater last ran) is greater than 5 days:
1. Open a `dom0` terminal
2. Run `/opt/securedrop/launcher/sdw-notify.py --skip-delta 0`

## Developer environment

The next version of Qubes will include PyQt5 in dom0, which is why we also support PyQt5.

### PyQt4 instructions

To run the preflight updater outside of `dom0`:
1. `cd securedrop-workstation/launcher`
2. Make the launcher script executable: `chmod +x sdw-launcher.py`
3. `sudo apt install python3-pyqt4`
4. Set up your virtual environment by running `make venv-pyqt4 && source .venv-pyqt4/bin/activate`
4. `export SDW_UPDATER_QT=4` (in case it was set to `5` when testing against PyQt5)
5. Now you can run the updater: `./sdw-launcher.py` (it won't actually update VMs unless you are in `dom0`)
6. You can also run the notifier: `./sdw-notify.py`

### PyQt5 instructions

To run the preflight updater outside of `dom0`:
1. `cd securedrop-workstation/launcher`
2. Make the launcher script executable: `chmod +x sdw-launcher.py`
3. Set up your virtual environment by running `make venv && source .venv/bin/activate`
4. `export SDW_UPDATER_QT=5`
5. Now you can run the updater: `./sdw-launcher.py` (it won't actually update VMs unless you are in `dom0`)
6. You can also run the notifier: `./sdw-notify.py`
