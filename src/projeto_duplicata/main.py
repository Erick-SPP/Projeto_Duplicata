import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QProgressBar, QMessageBox
)

# Import your backend engine and policy decorators
from .engine import base_processor, find_duplicates  # Adjust to match your exact function names
from .decorators import (
    text_file_policy,
    image_file_policy,
    video_file_policy,
    targeted_file_policy
)


class ScanWorker(QThread):
    """Runs the duplicate scan off the main UI thread."""
    finished = pyqtSignal(list)   # Emits list of duplicate groups: [[Path, Path], ...]
    error = pyqtSignal(str)

    def __init__(self, target_dir: Path, policy_mode: str, target_file: Path | None = None):
        super().__init__()
        self.target_dir = target_dir
        self.policy_mode = policy_mode
        self.target_file = target_file

    def run(self):
        try:
            # Select and decorate base_processor dynamically based on user choice
            if self.policy_mode == "Text Files":
                processor = text_file_policy(base_processor)
            elif self.policy_mode == "Images":
                processor = image_file_policy(base_processor)
            elif self.policy_mode == "Videos":
                processor = video_file_policy(base_processor)
            elif self.policy_mode == "Single Target File" and self.target_file:
                processor = targeted_file_policy(self.target_file)(base_processor)
            else:
                processor = base_processor  # Default global policy

            # Run your 3-pass pipeline using the decorated processor
            duplicates = find_duplicates(self.target_dir, processor)
            self.finished.emit(duplicates)

        except Exception as exc:
            self.error.emit(str(exc))


class DuplicateFinderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Policy-Driven Duplicate File Finder")
        self.resize(850, 550)

        self.selected_dir: Path | None = None
        self.selected_target_file: Path | None = None
        self.worker: ScanWorker | None = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Row 1: Folder & Policy Selection ---
        controls_layout = QHBoxLayout()

        self.dir_label = QLabel("No folder selected")
        self.btn_browse_dir = QPushButton("Select Folder...")
        self.btn_browse_dir.clicked.connect(self.choose_directory)

        self.policy_combo = QComboBox()
        self.policy_combo.addItems([
            "All Files (Global)",
            "Text Files",
            "Images",
            "Videos",
            "Single Target File"
        ])
        self.policy_combo.currentTextChanged.connect(self.on_policy_changed)

        self.btn_browse_file = QPushButton("Select Reference File...")
        self.btn_browse_file.setVisible(False)
        self.btn_browse_file.clicked.connect(self.choose_target_file)

        self.btn_scan = QPushButton("Start Scan")
        self.btn_scan.setEnabled(False)
        self.btn_scan.clicked.connect(self.start_scan)

        controls_layout.addWidget(self.btn_browse_dir)
        controls_layout.addWidget(self.dir_label, stretch=1)
        controls_layout.addWidget(QLabel("Policy:"))
        controls_layout.addWidget(self.policy_combo)
        controls_layout.addWidget(self.btn_browse_file)
        controls_layout.addWidget(self.btn_scan)
        layout.addLayout(controls_layout)

        # --- Row 2: Progress Indicator ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate spinner while scanning
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # --- Row 3: Duplicate Groups Tree ---
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Duplicate Group / File Path", "Size"])
        self.results_tree.setColumnWidth(0, 650)
        layout.addWidget(self.results_tree)

        # --- Row 4: Status Bar ---
        self.status_label = QLabel("Ready.")
        layout.addWidget(self.status_label)

    def choose_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if folder:
            self.selected_dir = Path(folder)
            self.dir_label.setText(str(self.selected_dir))
            self._update_scan_button_state()

    def choose_target_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Reference Document/File")
        if file_path:
            self.selected_target_file = Path(file_path)
            self.btn_browse_file.setText(self.selected_target_file.name)
            self._update_scan_button_state()

    def on_policy_changed(self, policy_text: str):
        is_single = (policy_text == "Single Target File")
        self.btn_browse_file.setVisible(is_single)
        self._update_scan_button_state()

    def _update_scan_button_state(self):
        if not self.selected_dir:
            self.btn_scan.setEnabled(False)
            return
        if self.policy_combo.currentText() == "Single Target File" and not self.selected_target_file:
            self.btn_scan.setEnabled(False)
            return
        self.btn_scan.setEnabled(True)

    def start_scan(self):
        if not self.selected_dir:
            return

        self.results_tree.clear()
        self.btn_scan.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Scanning directory...")

        self.worker = ScanWorker(
            target_dir=self.selected_dir,
            policy_mode=self.policy_combo.currentText(),
            target_file=self.selected_target_file
        )
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.start()

    def on_scan_finished(self, duplicate_groups: list):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)

        if not duplicate_groups:
            self.status_label.setText("Scan complete. No duplicates found.")
            return

        for idx, group in enumerate(duplicate_groups, start=1):
            group_item = QTreeWidgetItem(self.results_tree, [f"Duplicate Group #{idx} ({len(group)} files)", ""])
            for path in group:
                size_kb = f"{path.stat().st_size / 1024:.1f} KB" if path.exists() else "N/A"
                QTreeWidgetItem(group_item, [str(path), size_kb])
            group_item.setExpanded(True)

        self.status_label.setText(f"Scan complete. Found {len(duplicate_groups)} duplicate group(s).")

    def on_scan_error(self, message: str):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", message)
        self.status_label.setText("Scan failed.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DuplicateFinderWindow()
    window.show()
    sys.exit(app.exec())