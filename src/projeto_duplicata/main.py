import sys
from pathlib import Path
from typing import Optional, Any, Dict

from PyQt6.QtCore import Qt, QThread, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QProgressBar,
    QStatusBar,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from projeto_duplicata.engine import base_processor, find_duplicates
from projeto_duplicata.decorators import (
    text_file_policy,
    image_file_policy,
    video_file_policy,
    targeted_file_policy,
)


class ScanWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        target_dir: Path,
        mode_key: str,
        target_file: Optional[Path] = None,
    ):
        super().__init__()
        self.target_dir = target_dir
        self.mode_key = mode_key
        self.target_file = target_file

    def run(self):
        try:
            processor = base_processor
            if self.mode_key == "text":
                processor = text_file_policy(base_processor)
            elif self.mode_key == "image":
                processor = image_file_policy(base_processor)
            elif self.mode_key == "video":
                processor = video_file_policy(base_processor)
            elif self.mode_key == "targeted" and self.target_file:
                processor = targeted_file_policy(self.target_file)(base_processor)

            result = find_duplicates(
                self.target_dir,
                processor=processor,
                target_file=self.target_file if self.mode_key == "targeted" else None,
                is_cancelled=self.isInterruptionRequested,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class DuplicateFinderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projeto Duplicata — Policy-Driven Deduplicator")
        self.resize(1060, 680)

        self.target_dir: Optional[Path] = None
        self.target_file: Optional[Path] = None
        self.worker: Optional[ScanWorker] = None

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._apply_styles()

    def _setup_menu_bar(self):
        
        menu_bar =  menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar) 
        dir_menu = menu_bar.addMenu("&Directory")
        assert dir_menu is not None

        action_select_dir = QAction("Select Target Directory...", self)
        action_select_dir.setShortcut("Ctrl+O")
        action_select_dir.triggered.connect(self.select_directory)
        dir_menu.addAction(action_select_dir)

        action_select_ref = QAction("Select Reference File (Single-Target Mode)...", self)
        action_select_ref.setShortcut("Ctrl+Shift+O")
        action_select_ref.triggered.connect(self.select_reference_file)
        dir_menu.addAction(action_select_ref)

        dir_menu.addSeparator()

        action_exclusions = QAction("Manage Excluded Folders... (Future Update)", self)
        action_exclusions.setEnabled(False)
        dir_menu.addAction(action_exclusions)

        dir_menu.addSeparator()

        action_exit = QAction("Exit", self)
        action_exit.setShortcut("Ctrl+Q")
        action_exit.triggered.connect(self.close)
        dir_menu.addAction(action_exit)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- LEFT SIDEBAR: Plasticized Dark Policy Rail ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("PolicySidebar")
        self.sidebar.setFixedWidth(220)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(10)

        sidebar_title = QLabel("SCAN POLICIES")
        sidebar_title.setObjectName("SidebarHeader")
        sidebar_layout.addWidget(sidebar_title)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        # Replace `std_icon` with `QIcon("path/to/thumbnail.png")` later for custom thumbnails
        style = self.style()
        assert style is not None, "QStyle should be available for icon retrieval"
        modes = [
            ("global", "All Files (Global)", style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)),
            ("text", "Text Docs (< 1 MB)", style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)),
            ("image", "Images", style.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon)),
            ("video", "Videos", style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)),
            ("targeted", "Single Target File", style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)),
        ]

        self.mode_buttons: dict[str, QToolButton] = {}
        for idx, (key, label, icon) in enumerate(modes):
            btn = QToolButton()
            btn.setObjectName("PolicyButton")
            btn.setText(label)
            btn.setIcon(icon)
            btn.setIconSize(QSize(22, 22))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(btn.sizePolicy().horizontalPolicy(), btn.sizePolicy().verticalPolicy())
            btn.setMinimumHeight(46)
            btn.setMaximumWidth(192)

            if idx == 0:
                btn.setChecked(True)

            self.mode_group.addButton(btn)
            self.mode_buttons[key] = btn
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()
        root_layout.addWidget(self.sidebar)

        # --- RIGHT WORKSPACE: Target Bar, Scan Trigger & 3-Column Results ---
        workspace = QWidget()
        workspace.setObjectName("WorkspaceArea")
        ws_layout = QVBoxLayout(workspace)
        ws_layout.setContentsMargins(18, 16, 18, 14)
        ws_layout.setSpacing(12)

        # Top Action Header
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        self.lbl_target_dir = QLabel("Directory: None selected (use Directory → Select Target Directory...)")
        self.lbl_target_dir.setObjectName("TargetLabel")
        info_col.addWidget(self.lbl_target_dir)

        self.lbl_ref_file = QLabel("Reference File: None")
        self.lbl_ref_file.setObjectName("RefLabel")
        self.lbl_ref_file.setVisible(False)
        info_col.addWidget(self.lbl_ref_file)

        header_row.addLayout(info_col, stretch=1)

        #Start Scan Button
        self.btn_scan = QPushButton("Start Scan")
        self.btn_scan.setObjectName("PrimaryScanButton")
        self.btn_scan.setMinimumSize(130, 38)
        self.btn_scan.setEnabled(False)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self.start_scan)
        header_row.addWidget(self.btn_scan)

        # Cancel Scan Button (New)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryCancelButton")
        self.btn_cancel.setMinimumSize(100, 38)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.cancel_scan)
        header_row.addWidget(self.btn_cancel)

        ws_layout.addLayout(header_row)

        # Progress bar (indeterminate during active scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        ws_layout.addWidget(self.progress)

        # 3-Column Results Tree: Path | File Name | Size
        self.results_tree = QTreeWidget()
        self.results_tree.setColumnCount(3)
        self.results_tree.setHeaderLabels(["File Path", "File Name", "Size"])
        self.results_tree.setAlternatingRowColors(True)
        self.results_tree.setRootIsDecorated(True)
        self.results_tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        header = self.results_tree.header()
        assert header is not None

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        ws_layout.addWidget(self.results_tree, stretch=1)
        root_layout.addWidget(workspace, stretch=1)

    def _setup_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Ready — Select a target directory from the menu to begin.")

        # Subtle bottom-right permanent scan timer
        self.lbl_timing = QLabel("")
        self.lbl_timing.setObjectName("TimingTelemetry")
        status.addPermanentWidget(self.lbl_timing)

    def _apply_styles(self):
        self.setStyleSheet("""
            /* Plasticized Dark Sidebar with Layered Gradients & Solid Base */
            QFrame#PolicySidebar {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0.00 #121417,  /* Top-left: solid matte dark */
                    stop: 0.75 #121417,  /* Keeps the entire button area clean and un-obscured */
                    stop: 0.90 #1E293B,  /* Shadow buildup near bottom-right */
                    stop: 0.97 #38BDF8,  /* Icy blue corner flare */
                    stop: 1.00 #7DD3FC   /* Absolute bottom-right corner peak */
                );
                border-right: 1px solid #2D333F;
            }
                    
    
}

            QLabel#SidebarHeader {
                color: #94A3B8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.4px;
                padding-left: 4px;
                padding-bottom: 4px;
            }

            /* Glossy Card Buttons inside Sidebar */
            QToolButton#PolicyButton {
                color: #F1F5F9;
                font-size: 13px;
                font-weight: 500;
                padding: 8px 12px;
                border-radius: 8px;
                border-top: 1px solid rgba(255, 255, 255, 0.09);
                border-left: 3px solid transparent;
                border-right: 1px solid rgba(255, 255, 255, 0.04);
                border-bottom: 1px solid rgba(0, 0, 0, 0.45);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0.0 #1C2026,
                    stop: 0.5 #15181D,
                    stop: 1.0 #111317
                );
            }

            QToolButton#PolicyButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0.0 #262C36,
                    stop: 0.5 #1D222A,
                    stop: 1.0 #161920
                );
                border-top: 1px solid rgba(255, 255, 255, 0.18);
            }

            QToolButton#PolicyButton:checked {
                color: #FFFFFF;
                font-weight: 700;
                border-left: 4px solid #38BDF8;
                border-top: 1px solid rgba(125, 211, 252, 0.45);
                border-right: 1px solid rgba(56, 189, 248, 0.25);
                border-bottom: 1px solid #090B0E;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0.00 #1E293B,
                    stop: 0.48 #28384F,
                    stop: 0.52 #1E293B,
                    stop: 1.00 #172030
                );
            }

            /* Workspace & Action Controls */
            QLabel#TargetLabel {
                font-size: 13px;
                font-weight: 600;
                color: #1E293B;
            }

            QLabel#RefLabel {
                font-size: 12px;
                color: #0284C7;
                font-weight: 500;
            }

            QPushButton#PrimaryScanButton {
                background-color: #0F172A;
                color: #F1F5F9;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 16px;
            }

            QPushButton#PrimaryScanButton:hover:enabled {
                background-color: #1E293B;
            }

            QPushButton#PrimaryScanButton:disabled {
                background-color: #CBD5E1;
                color: #64748B;
            }

            /* Subtle Bottom-Right Scan Timer */
            QLabel#TimingTelemetry {
                color: #64748B;
                font-size: 11px;
                padding-right: 8px;
            }
        """)

    def select_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Directory")
        
        if folder:
            self.target_dir = Path(folder)
            self.lbl_target_dir.setText(f"Directory: {self.target_dir}")
            self.btn_scan.setEnabled(True)
            self.statusBar().showMessage(f"Target set to {self.target_dir}")

    def select_reference_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Master Reference File")
        if file_path:
            self.target_file = Path(file_path)
            self.lbl_ref_file.setText(f"Reference File: {self.target_file.name} ({self.target_file})")
            self.lbl_ref_file.setVisible(True)
            self.mode_buttons["targeted"].setChecked(True)
            self.statusBar().showMessage(f"Single-Target reference set: {self.target_file.name}")

    def _get_active_mode(self) -> str:
        for key, btn in self.mode_buttons.items():
            if btn.isChecked():
                return key
        return "global"

    def start_scan(self):
        if not self.target_dir:
            return

        mode_key = self._get_active_mode()
        if mode_key == "targeted" and not self.target_file:
            self.select_reference_file()
            if not self.target_file:
                return

        self.results_tree.clear()
        self.lbl_timing.setText("")
        self.btn_scan.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setVisible(True)
        self.statusBar().showMessage("Scanning directory...")

        self.worker = ScanWorker(
            target_dir=self.target_dir,
            mode_key=mode_key,
            target_file=self.target_file,
        )
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.start()

    def cancel_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.btn_cancel.setEnabled(False)
            status_bar = self.statusBar()
            assert status_bar is not None
            status_bar.showMessage("Cancelling scan...")

    def on_scan_finished(self, scan_result: dict):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        duplicate_groups = scan_result["duplicates"]
        t = scan_result["timings"]

        # Quiet bottom-right telemetry readout
        self.lbl_timing.setText(
            f"{t['files_scanned']:,} files | Total: {t['total_s']:.3f}s "
            f"(P1: {t['pass1_ms']:.1f}ms · P2: {t['pass2_ms']:.1f}ms · P3: {t['pass3_ms']:.1f}ms)"
        )

        if not duplicate_groups:
            self.statusBar().showMessage("Scan complete — No duplicate files found.")
            return

        bold_font = self.results_tree.font()
        bold_font.setBold(True)

        for idx, group in enumerate(duplicate_groups, start=1):
            group_item = QTreeWidgetItem(
                self.results_tree,
                [f"Duplicate Group #{idx} ({len(group)} files)", "", ""],
            )
            group_item.setFont(0, bold_font)

            for path in group:
                size_str = f"{path.stat().st_size / 1024:.1f} KB" if path.exists() else "N/A"
                row = QTreeWidgetItem(group_item, [str(path), path.name, size_str])
                # Highlight the File Name column so it pops visually for Windows search recovery
                row.setFont(1, bold_font)
                row.setForeground(1, QColor("#0369A1"))

            group_item.setExpanded(True)

        self.statusBar().showMessage(
            f"Found {len(duplicate_groups)} duplicate group(s). Double-click any row to copy its file name."
        )

    def on_scan_error(self, message: str):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.statusBar().showMessage(f"Error: {message}")

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        file_name = item.text(1) 
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        
        if file_name:
            clipboard.setText(file_name)
            self.statusBar().showMessage(f"Copied '{file_name}' to clipboard for Windows search.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DuplicateFinderWindow()
    window.show()
    sys.exit(app.exec())
