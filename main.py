import datetime
import math
import sys
import wave

import pyaudio
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QSlider, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Match, Base
from scoreboard_ui import Ui_ScoreBoard

engine = create_engine("sqlite:///tournament.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


def play_audio(filename):
    wf = wave.open(filename, 'rb')
    num_channels = wf.getnchannels()
    sample_width = wf.getsampwidth()
    frame_rate = wf.getframerate()
    num_frames = wf.getnframes()

    # Инициализируем PyAudio
    p = pyaudio.PyAudio()

    # Создаем поток
    stream = p.open(
        format=p.get_format_from_width(sample_width),
        channels=num_channels,
        rate=frame_rate,
        output=True
    )

    # Воспроизводим звук
    data = wf.readframes(num_frames)
    stream.write(data)

    # Закрываем поток и PyAudio
    stream.stop_stream()
    stream.close()
    p.terminate()


class MainWidget(QMainWindow):
    """
    Класс для автоматизации распределения команд
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Турнирная сетка")

        # Основной виджет и макет
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Слайдер для выбора количества участников
        self.slider_label = QLabel("Выберите количество участников:")
        self.layout.addWidget(self.slider_label)
        self.current_match_index = 0
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(2)
        self.slider.setMaximum(20)
        self.slider.setValue(2)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)
        self.layout.addWidget(self.slider)

        # Таблица для ввода названий команд
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Команды"])
        self.layout.addWidget(self.table)

        self.start_match_button = QPushButton("Начать матч")
        self.layout.addWidget(self.start_match_button)
        self.start_match_button.clicked.connect(self.start_next_match)

        # Переключатель между типами системы розыгрыша
        self.system_selector = QComboBox()
        self.system_selector.addItems(["Круговая система", "Олимпийская система"])
        self.layout.addWidget(self.system_selector)

        # Кнопка для генерации матчей
        self.generate_button = QPushButton("Сгенерировать турнирную сетку")
        self.layout.addWidget(self.generate_button)

        # Поле для вывода турнирной сетки
        self.matches_table = QTableWidget()
        self.layout.addWidget(self.matches_table)

        # Подключение сигналов
        self.slider.valueChanged.connect(self.update_table)
        self.generate_button.clicked.connect(self.generate_matches)

        # Инициализация таблицы
        self.update_table()
        self.load_matches_from_db()

    def start_next_match(self):
        """Закидывает матчи в табло."""
        matches = session.query(Match).all()
        match_index = self.get_current_match_index(matches)
        if match_index < len(matches):
            match = matches[match_index]
            if match.player1 == 'Бай' and match.player2 == 'Бай':
                self.record_winner(match, 'Бай')
            elif match.player2 == 'Бай':
                self.record_winner(match, match.player1)
            elif match.player1 == 'Бай':
                self.record_winner(match, match.player2)
            else:
                self.match_widget = MyWidget(name_team1=match.player1, name_team2=match.player2)
                self.match_widget.setWindowTitle(f"Матч: {match.player1} vs {match.player2}")

                # Сохранение победителя по завершению матча
                self.match_widget.match_finished.connect(lambda winner: self.record_winner(match, winner))

                self.match_widget.show()
        else:
            self.show_final_results()

    def update_table(self):
        """Обновляет таблицу на основе количества участников."""
        num_participants = self.slider.value()
        self.table.setRowCount(num_participants)
        for row in range(num_participants):
            if not self.table.item(row, 0):
                self.table.setItem(row, 0, QTableWidgetItem(f"Команда {row + 1}"))

    def generate_matches(self):
        """Генерирует турнирную сетку и сохраняет в базу данных."""
        system = self.system_selector.currentText()
        num_participants = self.slider.value()
        team_names = [self.table.item(row, 0).text() for row in range(num_participants) if self.table.item(row, 0)]

        # Удаляем старые матчи из базы данных
        session.query(Match).delete()
        session.commit()

        if system == "Круговая система":
            matches = self.generate_round_robin_matches(team_names)
        elif system == "Олимпийская система":
            matches = self.generate_elimination_matches(team_names)

        # Сохраняем матчи в базу данных
        for match in matches:
            db_match = Match(player1=match[0], player2=match[1], winner=None, system=system)
            session.add(db_match)
        session.commit()

        # Отображаем матчи в таблице
        self.load_matches_from_db()

    def generate_round_robin_matches(self, team_names):
        """Генерация матчей для круговой системы."""
        matches = []
        for i in range(len(team_names)):
            for j in range(i + 1, len(team_names)):
                matches.append((team_names[i], team_names[j]))
        return matches

    def generate_elimination_matches(self, team_names):
        """Генерация матчей для всех стадий олимпийской системы."""
        # Дополнение до ближайшей степени двойки
        next_power_of_two = 2 ** math.ceil(math.log2(len(team_names)))
        while len(team_names) < next_power_of_two:
            team_names.append("Бай")

        matches = []
        self.create_elimination_round(team_names, matches)
        return matches

    def create_elimination_round(self, teams, matches):
        """Рекурсивно генерирует раунды олимпийской системы."""
        if len(teams) == 1:  # Финал завершен
            return

        # Генерация матчей текущего раунда
        round_matches = [(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]
        matches.extend(round_matches)

        # Победители текущего раунда
        winners = [f"Победитель матча {len(matches) - len(round_matches) + i + 1}" for i in range(len(round_matches))]

        # Рекурсивный вызов для следующего раунда
        self.create_elimination_round(winners, matches)

    def record_winner(self, match, winner):
        match.winner = winner
        session.commit()

        # Обновляем следующую фазу матчей
        matches = session.query(Match).all()
        for i, m in enumerate(matches):
            # Проверяем, если текущий матч — это следующий этап
            if f"Победитель матча {match.id}" in (m.player1, m.player2):
                if m.player1 == f"Победитель матча {match.id}":
                    m.player1 = winner
                if m.player2 == f"Победитель матча {match.id}":
                    m.player2 = winner
                session.commit()

        self.load_matches_from_db()
        self.current_match_index += 1

        if self.current_match_index < len(matches):
            self.start_next_match()
        else:
            self.show_final_results()

    def show_final_results(self):
        winners = [match.winner for match in session.query(Match).all() if match.winner != "Бай"]
        winners = {team: winners.count(team) for team in set(winners)}
        sorted_winners = sorted(winners.items(), key=lambda x: x[1], reverse=True)
        # Выводим топ-3
        top_3 = "\n".join(
            [f"{i + 1} место: {team} ({wins} побед)" for i, (team, wins) in enumerate(sorted_winners[:3])])
        result_label = QLabel(f"Итоговые результаты:\n{top_3}")
        self.layout.addWidget(result_label)

    def load_matches_from_db(self):
        """Загружает матчи из базы данных и отображает в таблице."""
        matches = session.query(Match).all()

        self.matches_table.setRowCount(len(matches))
        self.matches_table.setColumnCount(3)
        self.matches_table.setHorizontalHeaderLabels(["Команда 1", "Команда 2", "Победитель"])

        for row, match in enumerate(matches):
            self.matches_table.setItem(row, 0, QTableWidgetItem(match.player1))
            self.matches_table.setItem(row, 1, QTableWidgetItem(match.player2))
            self.matches_table.setItem(row, 2, QTableWidgetItem(match.winner or "—"))

    def get_current_match_index(self, matches):
        for i, match in enumerate(matches):
            if match.winner is None:
                return i


class MyWidget(QMainWindow, Ui_ScoreBoard):
    """
    Табло для соревнований, игра заканчивается тогда, проходит 3
    тайм, выигрывает команда, которая набрала больше очков по истечению
    3 таймов,
    """
    match_finished = pyqtSignal(str)

    def __init__(self, name_team1: str = 'None', name_team2: str = 'None'):
        super().__init__()
        self.setupUi(self)
        self.dt = False
        self.ft = False
        self.pauseTF = True
        self.score_time1 = 0
        self.team1.clicked.connect(lambda: self.team_add(True))
        self.score_time2 = 0
        self.team2.clicked.connect(lambda: self.team_add(False))
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.match.display(str(1))
        self.time.setTime(datetime.time(0, 3))
        self.time.setDisplayFormat("mm:ss")
        self.pause.clicked.connect(self.make_pause)
        self.timer = QTimer()
        self.teamName1.setText(name_team1)
        self.teamName2.setText(name_team2)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.time.setStyleSheet("""
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                width: 0px;
                height: 0px;
            }
            QTimeEdit {
              background-color: #000080;
              color: #ff0000;
              border: 2px solid #ff0000;
              border-radius: 10px;
              font-size: 80px;
              font-weight: bold;
              padding: 5px;
            }
        """)
        self.pause.setIcon(QIcon(("img/pause.png")))
        self.restart.clicked.connect(self.all_reset)

    def team_add(self, is_team1):
        if is_team1:
            self.score_time1 += 1
            self.team1.setText(str(self.score_time1))
        else:
            self.score_time2 += 1
            self.team2.setText(str(self.score_time2))
        self.match.display(str(self.score_time1 + self.score_time2 + 1))
        if int(self.team1.text()) + int(self.team2.text()) == 3:
            if self.score_time1 > self.score_time2:
                winner = self.teamName1.toPlainText()
            elif self.score_time1 < self.score_time2:
                winner = self.teamName2.toPlainText()
            else:
                winner = "Ничья"

            self.match_finished.emit(winner)  # Отправка сигнала с именем победителя
            self.close()
        self.all_reset()

    def update_time(self):
        current_time = self.time.time()
        if self.dt:
            new_time = current_time.addSecs(+1)
            # print(new_time.hour(), new_time.minute(), new_time.second())
            if self.pauseTF:
                self.timerTF(ed=True)
            else:
                self.time.setTime(new_time)
        else:
            new_time = current_time.addSecs(-1)
            self.time.setTime(new_time)
            # print((new_time.hour(), new_time.minute(), new_time.second()),
            # (current_time.hour(), current_time.minute(), current_time.second()), sep='\t')
            if self.pauseTF:
                self.timerTF(ed=False)
            elif new_time.hour() == 0 and new_time.minute() == 0 and new_time.second() == 0:
                self.dop_time()

    def make_pause(self):
        self.pauseTF = not self.pauseTF
        self.update_time()
        if self.ft:
            self.pause.setIcon(QIcon(("img/pause.png")))
        else:
            self.pause.setIcon(QIcon(("img/play.png")))

    def timerTF(self, ed: bool = False):
        if self.ft:
            self.timer.start()
        else:
            self.timer.stop()
        current_time = self.time.time()
        if ed is False:
            new_time = current_time.addSecs(1)
        else:
            new_time = current_time.addSecs(0)
        self.time.setTime(new_time)
        self.pauseTF = not self.pauseTF
        self.ft = not self.ft

    def all_reset(self):
        self.time.setTime(datetime.time(0, 3))
        self.pauseTF = True
        self.ft = False
        self.dt = False
        self.match.setStyleSheet('''QLCDNumber {
                  background-color: #000080;
                  color: #ff0000;
                  border: 2px solid #ff0000;
                  border-radius: 10px;
                  font-size: 72px;
                  font-weight: bold;
                  padding: 10px;
                  text-align: center;
                }''')
        self.time.setStyleSheet("""
                                QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                        subcontrol-origin: margin;
                        subcontrol-position: top left;
                        width: 0px;
                        height: 0px;
                    }
                    QTimeEdit {
                      background-color: #000080;
                      color: #ff0000;
                      border: 2px solid #ff0000;
                      border-radius: 10px;
                      font-size: 80px;
                      font-weight: bold;
                      padding: 5px;
                    }""")
        self.pause.setIcon(QIcon(("img/pause.png")))

    def dop_time(self):
        self.dt = True
        # sound_file = "songs/svist.mp3"
        # self.player.setSource(QUrl.fromLocalFile(sound_file))
        # self.player.play()
        play_audio("songs/svist.wav")
        self.pauseTF = True
        self.match.setStyleSheet('''
            QLCDNumber {
              background-color: #ff0000;
              color: #000080;
              border: 2px solid #000080;
              border-radius: 10px;
              font-size: 72px;
              font-weight: bold;
              padding: 10px;
              text-align: center;
            }''')
        self.time.setStyleSheet("""
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                width: 0px;
                height: 0px;
            }
            QTimeEdit {
              background-color: #ff0000;
              color: #000080;
              border: 2px solid #000080;
              border-radius: 10px;
              font-size: 80px;
              font-weight: bold;
              padding: 5px;
            }

        """)
        self.pause.setIcon(QIcon(("img/pause.png")))
        self.ft = False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWidget()
    w.show()
    sys.exit(app.exec())
