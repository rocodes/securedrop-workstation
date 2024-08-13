#!/usr/bin/python3
"""
Admin wrapper script for applying salt states for staging and prod scenarios. The rpm
packages only puts the files in place `/srv/salt` but does not apply the state, nor
does it handle the config.
"""

import os
import subprocess
import sys
from enum import Enum
from typing import List
from PyQt5.QtCore import QObject, pyqtSignal


SCRIPTS_PATH = "/usr/share/securedrop-workstation-dom0-config/"
SALT_PATH = "/srv/salt/securedrop_salt/"

sys.path.insert(1, os.path.join(SCRIPTS_PATH, "scripts/"))
from validate_config import SDWConfigValidator, ValidationError  # noqa: E402

class SDWAdminException(Exception):
    pass

class ConfigStatus(Enum):
    CONNECT_SUCCESS = "CONNECT_SUCCESS",
    CONNECT_ERROR = "CONNECT_ERROR",
    VALIDATE_SUCCESS = "VALIDATE_SUCCESS",
    VALIDATE_ERROR = "VALIDATE_ERROR",
    APPLY_SUCCESS = "APPLY_SUCCESS",
    APPLY_ERROR = "APPLY_ERROR",
    UNKNOWN_ERROR = "UNKNONW_ERROR"

class SetupWorker(QObject):
    # QObject if we want to port to qProcess

    # Emit setup state
    state_changed = pyqtSignal(object)

    def __init__(self, parent: QObject | None = ...) -> None:
        super().__init__(parent)
        self.path_to_config = None

    def _install_pvh_support(self):
        """
        Installs grub2-xen-pvh in dom0 - required for PVH with AppVM local kernels
        TODO: install this via package requirements instead if possible
        """
        try:
            subprocess.check_call(["sudo", "qubes-dom0-update", "-y", "-q", "grub2-xen-pvh"])
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error installing grub2-xen-pvh: local PVH not available.")

    def _copy_config(self):
        """
        Copies config.json and sd-journalist.sec to /srv/salt/securedrop_salt
        """
        try:
            subprocess.check_call(["sudo", "cp", os.path.join(SCRIPTS_PATH, "config.json"), SALT_PATH])
            subprocess.check_call(
                ["sudo", "cp", os.path.join(SCRIPTS_PATH, "sd-journalist.sec"), SALT_PATH]
            )
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error copying configuration")

    def _provision_all(self):
        """
        Runs provision-all to apply the salt state.highstate on dom0 and all VMs
        """
        # TODO: make this separate scripts

        try:
            subprocess.check_call([os.path.join(SCRIPTS_PATH, "scripts/provision-all")])
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error during provision-all")

        print("Provisioning complete. Please reboot to complete the installation.")


    def _validate_config(self, path):
        """
        Calls the validate_config script to validate the config present in the staging/prod directory
        """
        try:
            validator = SDWConfigValidator(path)  # noqa: F841
        except ValidationError:
            raise SDWAdminException("Error while validating configuration")


    def _refresh_salt(self):
        """
        Cleans the Salt cache and synchronizes Salt to ensure we are applying states
        from the currently installed version
        """
        try:
            subprocess.check_call(["sudo", "rm", "-rf", "/var/cache/salt"])
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error while clearing Salt cache")

        try:
            subprocess.check_call(["sudo", "qubesctl", "saltutil.sync_all", "refresh=true"])
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error while synchronizing Salt")


    def _perform_uninstall(self):
        try:
            subprocess.check_call(
                ["sudo", "qubesctl", "state.sls", "securedrop_salt.sd-clean-default-dispvm"]
            )
            print("Destroying all VMs")
            subprocess.check_call([os.path.join(SCRIPTS_PATH, "scripts/destroy-vm"), "--all"])
            print("Reverting dom0 configuration")
            subprocess.check_call(["sudo", "qubesctl", "state.sls", "securedrop_salt.sd-clean-all"])
            subprocess.check_call([os.path.join(SCRIPTS_PATH, "scripts/clean-salt")])
            print("Uninstalling dom0 config package")
            subprocess.check_call(
                ["sudo", "dnf", "-y", "-q", "remove", "securedrop-workstation-dom0-config"]
            )
        except subprocess.CalledProcessError:
            raise SDWAdminException("Error during uninstall")

        print(
            "Instance secrets (Journalist Interface token and Submission private key) are still "
            "present on disk. You can delete them in /usr/share/securedrop-workstation-dom0-config"
        )

    def _check_euid(self):
        if os.geteuid() == 0:
            raise SDWAdminException("This wizard cannot be run as root.")

    def connect(self):
        try:
            available_vms = self.qubes_app.domains
            for vm in available_vms:
                if vm.name == "vault" and vm.netvm is None and vm.running: # todo
                    result = subprocess.run(["/usr/lib/qubes/qrexec-client", "-d", vm, "/etc/qubes-rpc/qubes.SelectDirectory"])
                    self.path_to_config = result.decode()
                    self.state_changed.emit(ConfigStatus.CONNECT_SUCCESS)
        except SDWAdminException:
            self.state_changed.emit(ConfigStatus.CONNECT_ERROR)

    def validate(self):
        try:
            self._validate_config(SCRIPTS_PATH)
            self.state_changed.emit(ConfigStatus.VALIDATE_SUCCESS)
        except SDWAdminException:
            self.state_changed.emit(ConfigStatus.VALIDATE_ERROR)        

    def apply(self):
        try:            
            self._validate_config(SCRIPTS_PATH)
            self._install_pvh_support()
            self._copy_config()
            self._refresh_salt()
            self._provision_all()

            self.state_changed.emit(ConfigStatus.APPLY_SUCCESS)
        except SDWAdminException:
            self.state_changed.emit(ConfigStatus.APPLY_ERROR)
    
    def uninstall(self):
        try:
            print(
                "Uninstalling will remove all packages and destroy all VMs associated\n"
                "with SecureDrop Workstation. It will also remove all SecureDrop tags\n"
                "from other VMs on the system."
            )
            self._refresh_salt()
            self._perform_uninstall()
        except SDWAdminException:
            pass # we aren't supporting uninstall
    