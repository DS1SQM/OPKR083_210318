#include <QLabel>
#include <QString>
#include <QScroller>
#include <QScrollBar>
#include <QPushButton>
#include <QGridLayout>
#include <QVBoxLayout>
#include <QDesktopWidget>

#include "common/params.h"
#include "onboarding.hpp"
#include "home.hpp"
#include "util.h"


void TrainingGuide::mouseReleaseEvent(QMouseEvent *e) {
  int leftOffset = (geometry().width()-1620)/2;
  int mousex = e->x()-leftOffset;
  int mousey = e->y();

  // Check for restart
  if (currentIndex == boundingBox.size()-1) {
    if (1050 <= mousex && mousex <= 1500 && 773 <= mousey && mousey <= 954){
      slayout->setCurrentIndex(0);
      currentIndex = 0;
      return;
    }
  }

  if (boundingBox[currentIndex][0] <= mousex && mousex <= boundingBox[currentIndex][1] && boundingBox[currentIndex][2] <= mousey && mousey <= boundingBox[currentIndex][3]) {
    slayout->setCurrentIndex(++currentIndex);
  }
  if (currentIndex >= boundingBox.size()) {
    emit completedTraining();
    return;
  }
}

TrainingGuide::TrainingGuide(QWidget* parent) {
  QHBoxLayout* hlayout = new QHBoxLayout;

  slayout = new QStackedLayout(this);
  for (int i = 0; i < boundingBox.size(); i++) {
    QWidget* w = new QWidget;
    w->setStyleSheet(".QWidget {background-image: url(../assets/training/step" + QString::number(i) + ".jpg);}");
    w->setFixedSize(1620, 1080);
    slayout->addWidget(w);
  }

  QWidget* sw = new QWidget();
  sw->setLayout(slayout);
  hlayout->addWidget(sw, 1, Qt::AlignCenter);
  setLayout(hlayout);
  setStyleSheet(R"(
    background-color: #072339;
  )");
}


QWidget* OnboardingWindow::terms_screen() {
  QVBoxLayout *main_layout = new QVBoxLayout;
  main_layout->setContentsMargins(40, 20, 40, 0);

  QString terms_html = QString::fromStdString(util::read_file("../assets/offroad/tc.html"));
  terms_text = new QTextEdit();
  terms_text->setReadOnly(true);
  terms_text->setTextInteractionFlags(Qt::NoTextInteraction);
  terms_text->setHtml(terms_html);
  main_layout->addWidget(terms_text);

  // TODO: add decline page
  QHBoxLayout* buttons = new QHBoxLayout;
  main_layout->addLayout(buttons);

  buttons->addWidget(new QPushButton("Decline"));
  buttons->addSpacing(50);

  QPushButton *accept_btn = new QPushButton("Scroll to accept");
  accept_btn->setEnabled(false);
  buttons->addWidget(accept_btn);
  QObject::connect(accept_btn, &QPushButton::released, [=]() {
    Params().write_db_value("HasAcceptedTerms", current_terms_version);
    updateActiveScreen();
  });

  // TODO: tune the scrolling
  auto sb = terms_text->verticalScrollBar();
#ifdef QCOM2
  sb->setStyleSheet(R"(
    QScrollBar {
      width: 150px;
      background: grey;
    }
    QScrollBar::handle {
      background-color: white;
    }
    QScrollBar::add-line, QScrollBar::sub-line{
      width: 0;
      height: 0;
    }
  )");
#else
  QScroller::grabGesture(terms_text, QScroller::TouchGesture);
  terms_text->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
#endif
  QObject::connect(sb, &QScrollBar::valueChanged, [sb, accept_btn]() {
    accept_btn->setEnabled(accept_btn->isEnabled() || (sb->value() == sb->maximum()));
  });

  QWidget *widget = new QWidget;
  widget->setLayout(main_layout);
  widget->setStyleSheet(R"(
    * {
      font-size: 50px;
    }
    QPushButton {
      padding: 50px;
      border-radius: 10px;
      background-color: #292929;
    }
  )");

  return widget;
}

void OnboardingWindow::updateActiveScreen() {
  Params params = Params();

  bool accepted_terms = params.get("HasAcceptedTerms", false).compare(current_terms_version) == 0;
  bool training_done = params.get("CompletedTrainingVersion", false).compare(current_training_version) == 0;
  if (!accepted_terms) {
    setCurrentIndex(0);
  } else if (!training_done) {
    setCurrentIndex(1);
  } else {
    emit onboardingDone();
  }
}

OnboardingWindow::OnboardingWindow(QWidget *parent) : QStackedWidget(parent) {
  Params params = Params();
  current_terms_version = params.get("TermsVersion", false);
  current_training_version = params.get("TrainingVersion", false);
  bool accepted_terms = params.get("HasAcceptedTerms", false).compare(current_terms_version) == 0;
  bool training_done = params.get("CompletedTrainingVersion", false).compare(current_training_version) == 0;

  // TODO: fix this, training guide is slow
  // Don't initialize widgets unless neccesary.
  if (accepted_terms && training_done) {
    return;
  }

  addWidget(terms_screen());

  TrainingGuide* tr = new TrainingGuide(this);
  connect(tr, &TrainingGuide::completedTraining, [=](){
    Params().write_db_value("CompletedTrainingVersion", current_training_version);
    updateActiveScreen();
  });
  addWidget(tr);

  setStyleSheet(R"(
    * {
      color: white;
      background-color: black;
    }
    QPushButton {
      padding: 50px;
      border-radius: 30px;
      background-color: #292929;
    }
    QPushButton:disabled {
      color: #777777;
      background-color: #222222;
    }
  )");

  updateActiveScreen();
}
