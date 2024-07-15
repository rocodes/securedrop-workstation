#!/usr/bin/python3
"""
SecureDrop Workstation Qubes 4.1 -> 4.2 Migration helper.
Meant to be run in dom0, this utility will collect credentials and assets for
migration from various parts of your QubesOS system.

At the end of this script the contents will be placed in a directory called "migration",
that should be transferred to a LUKS-encrypted drive attached to a non-networked VM (eg vault).

Note: dom0 in Qubes 4.1 uses Python 3.8.
"""

from enum import Enum
import logging
from pathlib import Path
import shutil
import subprocess
import sys

SDW_CONFIG_DIR = "/usr/share/securedrop-workstation-dom0-config"
SDW_CONFIG_FILES_DOM0 = ["config.json", "sd-journalist.sec"]
QUBES_DIR = "/etc/qubes"
DOM0_MIN_FREE_SPACE_BUFFER_KILOBYTES = 512000 # 500MB

logger = logging.getLogger(__name__)

class BackupStatus(Enum):
    COMPLETE = 0,
    INCOMPLETE = 1,

class BackupException(Exception):
    pass

class BackupTarget:
    def __init__(self, name, hint):
        self.name = name
        self.hint = hint

class BackupConfig:
    def __init__(self) -> None:
        super().__init__()
        self.backup_status = {}
        self.vms = [BackupTarget("dom0", "dom0 configuration files and /etc/qubes directory"), BackupTarget("sd-app", "/home/user/.securedrop_client directory", BackupTarget("sd-gpg", "sd-gpg GPG private keys"))]
        for vm in self.vms:
            self.backup_status[vm.name] = BackupStatus.INCOMPLETE

    def _intro(self):
        print("SecureDrop Workstation Qubes 4.1 -> 4.2 Migration helper")
        print("This script is meant to be run in dom0.")
        print("It will collect credentials and assets for migration from various parts of your QubesOS system.")
        print("Trust, but verify! Review this script before running it.")

        confirmation = input("Continue? (y/Y to continue, any key to quit)")
        if confirmation.lower() != "y":
            print("Aborting")
            sys.exit(1)
    
    def _qvm_run_io(self, vm, args: str, output_fd = None) -> str:
        """
        Run command in a given qube via qvm-run and return str-formatted output.
        If output_fd, representing an file descriptor, is provided, write directly to the
        output file. Otherwise write to stdout.
        """
        # qubesadmin.tools.qvm_run.main returns the exit code but prints the output to stderr,
        # whereas we want to capture the output, so use subprocess
        try:
            if output_fd:
                return subprocess.check_output(["qvm-run", "--pass-io", vm, args], stdout=output_fd).decode()
            else:
                return subprocess.check_output(["qvm-run", "--pass-io", vm, args]).decode()
        except subprocess.CalledProcessError as e:
            raise BackupException from e
    
    def _create_migration_dir(self):
        self.migration_dir = Path.mkdir(Path.cwd(), "migration")

    def _dom0(self):
        self.dom0_dir = Path.mkdir(self.migration_dir, "dom0")

        # /usr/share/securedrop-workstation-dom0-config
        for file in SDW_CONFIG_FILES_DOM0:
            shutil.copy(Path(SDW_CONFIG_DIR, file), self.dom0_dir)

        # Copy dom0 /etc/qubes (such as /etc/qubes/policy.d) to include in a dom0 backup
        shutil.copy(QUBES_DIR, self.migration_dir)

        # Store the GPG fingerprint from config.json
        with open(Path(self.dom0_dir, "config,json")) as f:
            for line in f:
                if "submission_key_fpr" in line.lower():
                    self.fingerprint = line.split()[1].strip()

        if len(self.fingerprint) == 40:
            self.backup_status["dom0"] = BackupStatus.COMPLETE
    
    def _list_fingerprints(self, gpg_console_lines: str) -> list[str]:
        """
        Helper to parse console output from `gpg` and return PGP fingerprints.
        Used with the str-formatted output of `gpg -K`, equivalent to
        `gpg -K --with-colons | grep "fpr" | cut -d: -f10` (and `wc -l`)
        """
        fingerprints = []
        gpg_console_lines = self._qvm_run_io("sd-gpg", "gpg -K --with-colons").split()
        for line in gpg_console_lines:
            if "fpr" in line:
                fingerprints.append(line.split(":")[9])

        return fingerprints

    def _sd_gpg(self):
        """
        Retrieve secret keys from sd-gpg, checking that at least one matches the fingerprint
        in config.json. 
        """
        sd_gpg_keys_name = "sd_secret_keys_armored.asc"
        self.sd_gpg_dir = Path.mkdir(self.migration_dir, "sd-gpg")
        remote_fprs = []
        local_fprs = []

        try:
            # qvm-run --pass-io sd-gpg "gpg -K --with-colons | grep fpr | cut -d: -f10"
            output = self._qvm_run_io("sd-gpg", "gpg -K --with-colons").split()

            remote_fprs = self._list_fingerprints(output)
            print(f"Found {len(remote_fprs)} key(s) to export from sd-gpg")

        except BackupException as e:
            logger.error(f"Failed to check sd-gpg keyring: {e}")

        # qvm-run --pass-io sd-gpg 'gpg -a --export-secret-keys' > sd-gpg/sd_secret_keys_armored.asc
        try:
            export_keys = self._qvm_run_io("sd-gpg", "gpg -a --export-secret-keys")
            with open(Path(self.sd_gpg_dir, sd_gpg_keys_name), "w+") as f:
                f.write(export_keys)

        except BackupException as ex:
            logger.error(f"Failed to export sd-gpg keyring: {ex}")

        # Create emphemeral gpg home directory and importing key(s) to check that import was
        # well-formed.C lean up afterwards by removing this directory.
        # Path.mkdir takes mode in decimal instead of octal. 0o700 = 448.
        tmp_gpg_dir = Path.mkdir(self.sd_gpg_dir, mode=448)
        gpg_args = ["gpg", "--homedir", str(tmp_gpg_dir), "--import", "-q", f"{self.sd_gpg_dir}/{sd_gpg_keys_name}"]
        gpg_check_args = ["gpg", "--homedir", str(tmp_gpg_dir), "-K", "--with-colons"]

        try:
            subprocess.check_call(gpg_args)
            gpg_output = subprocess.check_output(gpg_check_args).decode().split()

            local_fprs = self._list_fingerprints(gpg_output)
            print(f"Retrieved the following key(s):\n{local_fprs.join("\n")}")

        except subprocess.CalledProcessError as err:
            logger.error(f"Failed to recheck sd-gpg keys on dom0: {err}")

        finally:
            self._rm_gpgdir(tmp_gpg_dir)

        if self.fingerprint in local_fprs and len(local_fprs) == len(remote_fprs):
            self.backup_status["sd-gpg"] = BackupStatus.COMPLETE
        elif self.fingerprint not in local_fprs:
            print("Problem: Submission Key Fingerprint in config.json does not match any keys in sd-gpg.")
        else:
            print("Some keys may not have been imported successfully. Recheck sd-gpg keyring.")

    def _rm_gpgdir(self, target):
        """
        Helper. Delete gpg directory, first attempting to shred files in private_keys_v1.d. 
        """
        try:
            subprocess.check_call(["shred", "-u", f"{target}/private_keys_v1.d/*"])
        except subprocess.CalledProcessError:
            pass
        finally:
            shutil.rmtree(target)

    def _sd_app(self):
        self.sd_app_dir = Path.mkdir(self.migration_dir, "sd-app")
        # qvm-run --pass-io sd-app 'du -sh --block-size=1k /home/user/.securedrop_client' | cut -f1
        # kilobytes
        args = "du -sh --block-size=1k /home/user/.securedrop_client"

        try:
            data_size = self._qvm_run_io("sd-app", args).split[0]
            print("f{data_size} of uncompressed data on sd-app")
        
            # free_space_dom0=$(df -h /dev/mapper/qubes_dom0-root -k --output=avail | tail -n-1)
            # kilobytes
            dom0_args = ["df", "-h", "/dev/mapper/qubes_dom0-root", "-k", "--output=avail"]
            dom0_space = subprocess.check_output(dom0_args).decode().split()[1]

            # Small amoumts of coercion
            if int(dom0_space) - int(data_size) <= DOM0_MIN_FREE_SPACE_BUFFER_KILOBYTES:

                # We'd probably be fine; the backup will compress and we won't be cutting it this close.
                # But err on the side of caution and don't fill up dom0.
                print("Problem: /home/user.securedrop_client on sd-app is too large to transfer.")
                print("Please back up sd-app manually using the Qubes GUI backup tool and a strong backup passphrase.")
                print("For assistance, contact Support.")

            else:
                # qvm-run --pass-io sd-app 'tar -cz -C /home/user .securedrop_client' > sd-app/securedrop_client.tar.gz
                # This could be a lot of data, so write it to a file instead of stdout so as not to fill the pipe.
                with open(Path(self.sd_app_dir, "securedrop_client.tar.gz"), "w+") as archive:
                    self._qvm_run_io(vm="sd-app", args="tar -cz -C /home/user .securedrop_client", output_fd=archive)

        except (BackupException, subprocess.CalledProcessError):
            # todo
            pass

    def _print_final_instructions(self):
        print("You are responsible for preserving any of your own customizations, eg via the Qubes Backup tool.")
        print("Please transfer the migration directory, and all its contents, to a non-networked VM (vault), using qvm-copy-to-vm.")
        print("Then, transfer the directory to a LUKS-encrypted transfer device.")
        print("Important: at the end of this migration process, wipe and reformat or destroy that drive.")

    def all(self):
        """
        Gathers:
            - config.json, sd-journalist.sec from /usr/share/securedrop-workstation-dom0-config
            - secret keys from sd-gpg
            - .securedrop_client directory (compressed) from sd-app, if dom0 disk space permits

        Checks:
            - Fingerprint in config.json matches a secret key from sd-gpg
            - Fingerprint in config.json matches key exported from sd-gpg into dom0 (successful export)
            - sd-app .securedrop_client directory successfully imported into dom0

        Prints success message if backup has completed successfully, otherwise provides information about
        which part of the process failed.
        """
        self._intro()
        self._dom0()
        self._sd_gpg()
        self._sd_app()

        if BackupStatus.INCOMPLETE not in self.backup_status.values():
            print("Credentials and secrets have been collected successfully in the 'migration' directory.")
            print("This is not a system backup! Only SecureDrop-Workstation specific configuration files and dom0 files in /etc/qubes have been preserved.")
        else:
            print("Failed to gather all required assets - additional steps required.")
            print("You will need to manually add the missing files to the 'migration' directory.")
            for entry in self.backup_status.keys():
                print(f"{entry.name}: [success, no action required]") if self.backup_status[entry] == BackupStatus.COMPLETE else print(f"{entry.name}: {entry.hint}")

        self._print_final_instructions()

if __name__ == "__main__":
    BackupConfig().all()
