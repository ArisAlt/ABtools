// ABtools/AbtoolsGui.cpp · v0.1 · 2025-09-01
// Simple Qt GUI wrapper around existing ABtools Python scripts

#include <QApplication>
#include <QCheckBox>
#include <QFileDialog>
#include <QGridLayout>
#include <QLineEdit>
#include <QMainWindow>
#include <QMessageBox>
#include <QProcess>
#include <QProgressBar>
#include <QPushButton>
#include <QTextEdit>
#include <QLabel>
#include <QStatusBar>
#include <QCoreApplication>
#include <QTextStream>

#include <filesystem>

static const char* VERSION = "0.1";
static const char* FILE_PATH = __FILE__;

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    MainWindow() {
        setWindowTitle("ABtools GUI");

        auto *central = new QWidget(this);
        auto *layout = new QGridLayout(central);

        srcEdit = new QLineEdit(this);
        dstEdit = new QLineEdit(this);
        planEdit = new QLineEdit(this);

        auto *browseSrc = new QPushButton("Browse", this);
        auto *browseDst = new QPushButton("Browse", this);
        auto *browsePlan = new QPushButton("Browse", this);

        connect(browseSrc, &QPushButton::clicked, this, [this]() {
            auto dir = QFileDialog::getExistingDirectory(this, "Source Folder");
            if (!dir.isEmpty()) srcEdit->setText(dir);
        });
        connect(browseDst, &QPushButton::clicked, this, [this]() {
            auto dir = QFileDialog::getExistingDirectory(this, "Destination Folder");
            if (!dir.isEmpty()) dstEdit->setText(dir);
        });
        connect(browsePlan, &QPushButton::clicked, this, [this]() {
            auto file = QFileDialog::getSaveFileName(this, "Plan JSON", QString(), "JSON (*.json)");
            if (!file.isEmpty()) planEdit->setText(file);
        });

        layout->addWidget(new QLabel("Source"), 0, 0);
        layout->addWidget(srcEdit, 0, 1);
        layout->addWidget(browseSrc, 0, 2);

        layout->addWidget(new QLabel("Destination"), 1, 0);
        layout->addWidget(dstEdit, 1, 1);
        layout->addWidget(browseDst, 1, 2);

        layout->addWidget(new QLabel("Plan JSON"), 2, 0);
        layout->addWidget(planEdit, 2, 1);
        layout->addWidget(browsePlan, 2, 2);

        commitBox = new QCheckBox("Commit", this);
        copyBox = new QCheckBox("Copy", this);
        yesBox = new QCheckBox("Yes", this);
        layout->addWidget(commitBox, 3, 0);
        layout->addWidget(copyBox, 3, 1);
        layout->addWidget(yesBox, 3, 2);

        output = new QTextEdit(this);
        output->setReadOnly(true);
        layout->addWidget(output, 4, 0, 1, 3);

        progress = new QProgressBar(this);
        progress->setRange(0, 0); // indeterminate
        layout->addWidget(progress, 5, 0, 1, 3);

        auto *runBtn = new QPushButton("Run", this);
        auto *restructureBtn = new QPushButton("Restructure", this);
        auto *tagBtn = new QPushButton("Tag Only", this);
        auto *dupesBtn = new QPushButton("Find Duplicates", this);
        auto *planBtn = new QPushButton("Make Plan", this);
        auto *applyBtn = new QPushButton("Apply Plan", this);

        layout->addWidget(runBtn, 6, 0);
        layout->addWidget(restructureBtn, 6, 1);
        layout->addWidget(tagBtn, 6, 2);
        layout->addWidget(dupesBtn, 7, 0);
        layout->addWidget(planBtn, 7, 1);
        layout->addWidget(applyBtn, 7, 2);

        setCentralWidget(central);

        process = new QProcess(this);
        connect(process, &QProcess::readyReadStandardOutput, this, [this]() {
            output->append(process->readAllStandardOutput());
        });
        connect(process, &QProcess::readyReadStandardError, this, [this]() {
            output->append(process->readAllStandardError());
        });
        connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int, QProcess::ExitStatus){
            progress->setRange(0, 1);
            progress->setValue(1);
            statusBar()->showMessage("Done", 3000);
        });

        connect(runBtn, &QPushButton::clicked, this, &MainWindow::runCombobook);
        connect(restructureBtn, &QPushButton::clicked, this, &MainWindow::runRestructure);
        connect(tagBtn, &QPushButton::clicked, this, &MainWindow::runTagOnly);
        connect(dupesBtn, &QPushButton::clicked, this, &MainWindow::runDupes);
        connect(planBtn, &QPushButton::clicked, this, &MainWindow::makePlan);
        connect(applyBtn, &QPushButton::clicked, this, &MainWindow::applyPlan);
    }

private:
    QLineEdit *srcEdit, *dstEdit, *planEdit;
    QCheckBox *commitBox, *copyBox, *yesBox;
    QTextEdit *output;
    QProgressBar *progress;
    QProcess *process;

    QStringList baseArgs() const {
        QStringList args;
        if (commitBox->isChecked()) args << "--commit";
        if (copyBox->isChecked()) args << "--copy";
        if (yesBox->isChecked()) args << "--yes";
        return args;
    }

    void runPython(const QString &script, const QStringList &extra) {
        if (process->state() != QProcess::NotRunning) {
            QMessageBox::warning(this, "Busy", "A process is already running.");
            return;
        }
        output->clear();
        progress->setRange(0, 0); // indeterminate
        QStringList args;
        args << script;
        args << extra;
        process->start("python3", args);
        if (!process->waitForStarted()) {
            QMessageBox::critical(this, "Error", "Failed to start python process");
            progress->setRange(0,1);
            progress->setValue(0);
        }
    }

    void runCombobook() {
        QStringList args = baseArgs();
        args << srcEdit->text() << dstEdit->text();
        runPython("combobook.py", args);
    }
    void runRestructure() {
        QStringList args = baseArgs();
        args << srcEdit->text() << dstEdit->text();
        runPython("restructure_for_audiobookshelf.py", args);
    }
    void runTagOnly() {
        QStringList args = baseArgs();
        args << srcEdit->text();
        runPython("search_and_tag.py", args);
    }
    void runDupes() {
        QStringList args = baseArgs();
        args << srcEdit->text() << dstEdit->text();
        runPython("find_duplicates.py", args);
    }
    void makePlan() {
        QStringList args = baseArgs();
        args << srcEdit->text() << dstEdit->text() << "--plan-json" << planEdit->text();
        runPython("restructure_for_audiobookshelf.py", args);
    }
    void applyPlan() {
        QStringList args;
        args << "--apply-plan" << planEdit->text();
        runPython("transaction.py", args);
    }
};

#include "AbtoolsGui.moc"

int main(int argc, char *argv[]) {
    QCoreApplication::setApplicationName("AbtoolsGui");
    QApplication app(argc, argv);
    QStringList args = app.arguments();
    if (args.contains("--version")) {
        QTextStream(stdout) << QString("%1 v%2 (%3)\n").arg(QCoreApplication::applicationName(), VERSION, FILE_PATH);
        return 0;
    }
    MainWindow w;
    w.show();
    return app.exec();
}

