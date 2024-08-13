
import re
from enum import IntEnum
from typing import List

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QAbstractButton, QWidget, QWizard, QWizardPage, QPushButton, QMenu, QAction, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QButtonGroup

from sdw_admin import SetupWorker, SDWAdminException, ConfigStatus

import qubesadmin

class SetupPages(IntEnum):
    PREAMBLE_PAGE = 0,
    ERROR_PAGE = 1,
    CONNECT_SECRETS_PAGE = 2,
    # Optional: a Tails setup means both SVS+admin stick have the necessaries on them
    CONNECT_TAILSCONFIG_PAGE = 3,
    VALIDATE_PAGE = 4,
    APPLY_PAGE = 5,
    RESULT_PAGE_SUCCESS = 6,

DISPLAY_TEXT = {
    SetupPages.PREAMBLE_PAGE: ("SecureDrop Workstation Configuration", "Welcome to SDW Configuration Tool. This tool will guide you through installing SecureDrop Workstation."),
    SetupPages.ERROR_PAGE: ("Setup Error", "Error during setup"),
    SetupPages.CONNECT_SECRETS_PAGE: ("Connect Encrypted Storage", "Please connect encrypted storage device to a <strong>non-networked</strong> VM such as Vault"),
    SetupPages.CONNECT_TAILSCONFIG_PAGE: ("Connect Encrypted Storage", "Please connect Tails Admin Workstation to a <strong>non-networked</strong> VM such as Vault"),
    SetupPages.VALIDATE_PAGE: ("Validate Configuratin", "This will validate the configuration you provided"),
    SetupPages.APPLY_PAGE: ("Install SecureDrop Workstation", "Applying Configuration (this will take some time...)"),
    SetupPages.RESULT_PAGE_SUCCESS: ("Setup Complete", "Successfully configured. Please reboot now."),
}

BASE_TEMPLATE = "debian-12-minimal"

class SetupWizard(QWizard):
    """
    SDW Setup Wizard.
    """
    def __init__(self, worker: SetupWorker, parent: QWidget | None = ..., flags: Qt.WindowFlags | Qt.WindowType = ...) -> None:
        super().__init__(parent, flags)
        self._set_layout()
        self._set_pages()
        self.adjustSize()
        self.qubes_app = qubesadmin.Qubes()

        # Connect handlers
        self.worker.state_changed.connect(self.on_step_complete)
        
        # Connect buttons
        self.next_button: QAbstractButton = self.button(QWizard.WizardButton.NextButton)
        self.cancel_button: QAbstractButton = self.button(QWizard.WizardButton.CancelButton)
        self.back_button: QAbstractButton = self.button(QWizard.WizardButton.BackButton)
        self.finish_button: QAbstractButton = self.button(QWizard.WizardButton.FinishButton)

        self.next_button.clicked.connect(self.run_step)

    def _set_pages(self) -> None:
        for page in SetupPages:

            # Set up and populate different pages of the wizard
            self.setPage(page.value, SetupWizardPage(page))

    def _set_layout(self) -> None:
        title = f"SDW Configuration Tool" # todo
        self.setWindowTitle(title)
        self.setObjectName("SDW_Wizard") # Could use same styling as all other wizards eg
        self.setModal(False)
        self.setOptions(
            QWizard.NoBackButtonOnLastPage
            | QWizard.NoCancelButtonOnLastPage
            | QWizard.NoBackButtonOnStartPage
        )

    @pyqtSlot()
    def run_step(self) -> None:
        page = self.currentPage()
        self.next_button.setEnabled(False)

        # not sure about this
        if isinstance(page, SetupWizardPage):
            page.set_complete(False)

        if self.currentPage == SetupPages.CONNECT_SECRETS_PAGE:
            self.worker.connect()
        elif self.currentPage == SetupPages.VALIDATE_PAGE:
            self.worker.validate()
        elif self.currentPage == SetupPages.APPLY_PAGE:
            self.worker.apply()

    @pyqtSlot(object)
    def on_step_complete(self, status: ConfigStatus):
        self.status = status
        self.next_button.setEnabled(True)

        # Confirm
        self.currentPage().next()

    @pyqtSlot(object)
    def on_step_error(self, err: SDWAdminException):
        pass # TODO
   

class SetupWizardPage(QWizardPage):
    """
    A page in the SDW Setup wizard.
    """
    NO_MARGIN = 0

    def __init__(self, page_type: SetupPages, parent: QWidget | None = ...) -> None:
        super().__init__(parent)
        self.page_type = page_type
        self.status = None
        # By default, pages can't advance without the set_complete method being called
        self._is_complete = False
        self._build_layout()
        self.header_text = DISPLAY_TEXT.get(page_type)[0] # TODO
        self.body_text = DISPLAY_TEXT.get(page_type)[1] # TODO
        self._layout = self._build_layout()
        self.setLayout(self._layout)

    def _build_layout(self) -> QVBoxLayout:
        """
        Create parent layout, draw elements, return parent layout.
        """
        self.setObjectName("SDW_Setup_Page")

        parent_layout = QVBoxLayout(self)
        #parent_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)

        # Header for icon and task title
        header_container = QWidget()
        header_container_layout = QHBoxLayout()
        header_container.setLayout(header_container_layout)
        header_container.setContentsMargins(
            self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN
        )
        
        header = QLabel()
        header.setObjectName("QWizard_header")
        header_container_layout.addWidget(header, alignment=Qt.AlignCenter)
        header_container_layout.addStretch()
        header_line = QWidget()
        header_line.setObjectName("QWizard_header_line") # todo

        # Body to display instructions and forms
        body = QLabel()
        body.setObjectName("QWizard_body")
        body.setWordWrap(True)
        body.setScaledContents(True)

        body_container = QWidget()
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(
            self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN
        )
        body_container.setLayout(body_layout)
        body_layout.addWidget(body)

        # Widget for displaying error messages (hidden by default)
        self.error_details = QLabel()
        self.error_details.setObjectName("QWizard_error_details")
        self.error_details.setWordWrap(True)
        self.error_details.hide()

        # Populate text content
        header.setText(self.header_text)
        body.setText(self.body_text)

        # Add all the layout elements
        parent_layout.addWidget(header_container)
        parent_layout.addWidget(header_line)
        parent_layout.addWidget(body_container)
        parent_layout.addWidget(self.error_details)
        parent_layout.addStretch()

        return parent_layout

    def nextId(self) -> int:
        if self.wizard():
            status = self.wizard().status
            if status in [ConfigStatus.APPLY_ERROR, ConfigStatus.CONNECT_ERROR, ConfigStatus.VALIDATE_ERROR]:
                return SetupPages.ERROR_PAGE
            elif self.page_type == SetupPages.PREAMBLE_PAGE:
                return SetupPages.CONNECT_SECRETS_PAGE

        return super().nextId()

    def isComplete(self):
        """
        Overrides builtin method, caps case intentional 
        """
        return super().isComplete() and self._is_complete

    def set_complete(self, is_complete: bool):
        self._is_complete = is_complete

class SelectDeviceTypePage(SetupWizardPage):
    """
    Wizard page that lets the user select either
    Tails or SDW backup for importing configuration.
    """
    def __init__(self, page_type: SetupPages, parent: QWidget | None = ...) -> None:
        super().__init__(page_type, parent)

    def _build_layout(self) -> QVBoxLayout:
        layout = super()._build_layout()

        choose_storage_type_layout = QHBoxLayout()
        choose_header = QLineEdit()
        choose_header.setText("IMPORT CONFIGURATION DETAILS")

        choose_radio_group = QButtonGroup()
        self.button_tails = QRadioButton()
        self.button_tails.setText("FROM TAILS")
        self.button_backup = QRadioButton()
        self.button_backup.setText("FROM A CONFIGURATION BACKUP")

        choose_radio_group.addButton(self.button_tails)
        choose_radio_group.addButton(self.button_backup)

        choose_radio_group.buttonClicked.connect(self._on_radio_selection)

        choose_storage_type_layout.addItem(choose_header)
        choose_storage_type_layout.addStretch()
        choose_storage_type_layout.addItem(choose_radio_group)
        choose_storage_type_layout.addStretch()

        layout.insertWidget(1, choose_storage_type_layout)
        return layout
    
    def _on_radio_selection(self):
        """
        The RadioGroup enforces that one button must be selected.
        For now, just register the Tails button. If more than two
        options are offered in future, all fields should be registered.
        """
        self.registerField("button_tails*", self.button_tails)

        # Once a selection is made, this screen is complete
        self.set_complete(True)

class DirectoryPickerPage(SetupWizardPage):
    def __init__(self, parent: QWidget | None = ...) -> None:
        super().__init__(parent)
        self.vm = None # Holds selected vm where USB is attached.

    def _build_layout(self) -> QVBoxLayout:
        layout = super()._build_layout()

        # VM chooser
        choose_vm_layout = QHBoxLayout()
        choose_vm_label = QLabel()
        choose_vm_label.setText("VM where storage device is mounted")
        choose_vm_menu = QMenu()
        vms = self._get_running_vms()
        for entry in vms:
            choose_vm_menu.addAction(self._menu_action(entry))
        
        choose_vm_layout.addItem(choose_vm_label)
        choose_vm_layout.addItem(choose_vm_menu)

        # Directory
        storage_dir_form = QWidget()
        storage_dir_form.setObjectName("QWizard_passphrase_form")
        storage_dir_form_layout = QVBoxLayout()
        storage_dir_form_layout.setContentsMargins(
            self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN, self.NO_MARGIN
        )
        storage_dir_form.setLayout(storage_dir_form_layout)
        storage_dir_label = ("Select Storage Directory")

        storage_dir_and_overflow = QHBoxLayout()
        self.storage_dir = QLineEdit()

        self.button_select_storage_dir = QPushButton()
        self.button_select_storage_dir.setText("...") # TODO - icon instead
        self.button_select_storage_dir.clicked.connect(self.get_path_from_vm)

        storage_dir_and_overflow.addItem(self.storage_dir)
        storage_dir_and_overflow.addItem(self.button_select_storage_dir)

        storage_dir_form_layout.addWidget(storage_dir_label)
        storage_dir_form_layout.addWidget(storage_dir_and_overflow)

        layout.insertWidget(1, choose_vm_layout)
        layout.insertWidget(2, storage_dir_form)
        return layout

    def _menu_action(self, vm) -> QAction:
        action = QAction()
        action.setText(vm.name)
        action.triggered.connect(lambda vm: self._on_item_clicked(vm))
        return action

    @pyqtSlot()
    def _on_item_clicked(self, vm):
        self.vm = vm

    def _get_running_vms(self):
        vms = []
        available_vms = self.qubes_app.domains
        for vm in available_vms:
            if vm.name == "vault" and vm.netvm is None and vm.running: # todo
                vms.append(vm)
        return vms

    # From Qubes manager.py 
    def get_path_from_vm(self):
        """
        Displays a file/directory selection window for the given VM.

        :param vm: vm from which to select path
        :return: path to file, checked for validity
        """
        vm = self.target_vm

        path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() ?-]*")
        path_max_len = 512

        if not vm:
            return None
        stdout, _stderr = vm.run_service_for_stdio("qubes.SelectDirectory")

        stdout = stdout.strip()

        untrusted_path = stdout.decode(encoding='ascii')[:path_max_len]

        if untrusted_path and path_re.fullmatch(untrusted_path):
            assert '../' not in untrusted_path
            assert '\0' not in untrusted_path
            self.storage_dir.setText(untrusted_path.strip())
            self.set_complete(True)
        
        self.registerField("storage_dir_secrets*", self.storage_dir)
    
        raise ValueError("Unexpected characters in path.")

class ConfirmationPage(SetupWizardPage):
    def __init__(self, page_type: SetupPages, parent: QWidget | None = ...) -> None:
        body_text = self._confirm_running_vms()
        super().__init__(page_type, parent=parent)
        self.set_complete(True)

    def _build_layout(self):
        layout = super()._build_layout()

    def _confirm_running_vms(self):
        body_text = (
            "SecureDrop Workstation should always be installed on a fresh Qubes OS install. "
            "The installation process will overwrite any user modifications to the "
            f"{BASE_TEMPLATE} TemplateVM, and will disable old-format qubes-rpc "
            "policy directives.\n"
        )
        affected_appvms = self._get_appvms_for_template(BASE_TEMPLATE)
        if len(affected_appvms) > 0:
            body_text += (
                f"{BASE_TEMPLATE} is already in use by the following AppVMS:\n"
                f"{affected_appvms}\n"
                "Applications and configurations in use by these AppVMs will be\n"
                f"removed from {BASE_TEMPLATE}."
            )
        
        return body_text

    def _get_appvms_for_template(self, vm_name: str) -> List[str]:
        """
        Return a list of AppVMs that use the specified VM as a template
        """
        try:
            template_vm = self.qubes_app.domains[vm_name]
        except KeyError:
            # No VM implies no appvms, return an empty list
            # (The template may just not be installed yet)
            return []
        return [x.name for x in list(template_vm.appvms)]
    
