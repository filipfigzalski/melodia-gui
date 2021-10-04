import os
import sys

# Logging
import logging as l

# Random number generation
import random

# Handling configuration file
import configparser
import codecs

# Audio playback and bitrate check
import wave
from pygame import mixer
from mutagen import mp3

# PyQt5
from PyQt5 import uic, QtTest
from PyQt5.QtGui import QFontDatabase, QFont, QKeyEvent
from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtCore import QTimer, QUrl, Qt

# Serial connection handling
import serial
from serial.tools import list_ports

# Spotify
import spotipy
from spotipy import cache_handler
from spotipy.cache_handler import CacheFileHandler
from spotipy.client import Spotify
from spotipy.oauth2 import SpotifyOAuth

MAX_TEAM_NUMBER = 6

class Ui(QMainWindow):
    '''Main Window'''

    S_PLAYING = 0
    S_PAUSED = 1
    S_STOPPED = 2

    def __init__(self) -> None:
        super().__init__()
        uic.loadUi('data/window.ui', self)

        # Logging.
        l.basicConfig()
        l.info('Starting program.')

        self.serial = serial.Serial()  # Used for serial connection to Arduino.

        # Used for playing music
        mixer.init()

        # Stores dictionary conaining data of currently playing song
        self.current_song: str = None
        self.guessing_team: int = None  # Stores index of team that pressed button first
        # Stores current state of game (S_PLAYING, S_STOPPED, S_PAUSED, S_GUESSING)
        self.playback_state: int = self.S_PAUSED
        self.is_team_guessing: bool = False
        self.millis: int = 0  # Position of the song
        self.team_scores: list[int] = [0, 0, 0, 0, 0, 0]  # Scores of each team

        # Loading widgets
        # Title of the song.
        self.label_title: QLabel = self.findChild(QLabel, 'l_title')
        # Artist of the song.
        self.label_artist: QLabel = self.findChild(QLabel, 'l_artist')
        # Name of team that pressed button.
        self.label_team: QLabel = self.findChild(QLabel, 'l_team')
        # Percent of song that played.
        self.label_timer: QLabel = self.findChild(QLabel, 'l_timer')
        # Status of connection to Arduino.
        self.label_status: QLabel = self.findChild(QLabel, 'l_status')
        self.label_team_names: list[QLabel] = [
            self.findChild(QLabel, 'l_team1n'),
            self.findChild(QLabel, 'l_team2n'),
            self.findChild(QLabel, 'l_team3n'),
            self.findChild(QLabel, 'l_team4n'),
            self.findChild(QLabel, 'l_team5n'),
            self.findChild(QLabel, 'l_team6n'),
        ]  # Names of the teams.
        self.label_team_scores: list[QLabel] = [
            self.findChild(QLabel, 'l_team1s'),
            self.findChild(QLabel, 'l_team2s'),
            self.findChild(QLabel, 'l_team3s'),
            self.findChild(QLabel, 'l_team4s'),
            self.findChild(QLabel, 'l_team5s'),
            self.findChild(QLabel, 'l_team6s'),
        ]  # Scores of the teams.
        self.widget_team: list[QWidget] = [
            self.findChild(QWidget, 'w_team1'),
            self.findChild(QWidget, 'w_team2'),
            self.findChild(QWidget, 'w_team3'),
            self.findChild(QWidget, 'w_team4'),
            self.findChild(QWidget, 'w_team5'),
            self.findChild(QWidget, 'w_team6'),
        ]
        # Opens settings dialog.
        self.button_settings: QPushButton = self.findChild(
            QPushButton, 'b_settings')
        # Plays next song.
        self.button_next: QPushButton = self.findChild(QPushButton, 'b_next')
        # Pauses or resumes current song.
        self.button_pause_resume: QPushButton = self.findChild(
            QPushButton, 'b_pause_resume')
        # Team gave correct answer.
        self.button_yes: QPushButton = self.findChild(QPushButton, 'b_yes')
        # Team gave incorrect answer.
        self.button_no: QPushButton = self.findChild(QPushButton, 'b_no')
        # Progress bar displaying how much into the song we are.
        self.progress_bar: QProgressBar = self.findChild(
            QProgressBar, 'p_progress')

        # Creating timers
        # Reads serial date every 100ms.
        self.timer_serial: QTimer = QTimer(self)
        # Updates progress bar and checks if song is over.
        self.timer_song: QTimer = QTimer(self)

        # Attaching functions to widgets
        self.button_settings.clicked.connect(self.open_settings)
        self.button_next.clicked.connect(self.next_playback)
        self.button_pause_resume.clicked.connect(self.pause_resume)
        self.button_yes.clicked.connect(self.answer_correct)
        self.button_no.clicked.connect(self.answer_incorrect)

        self.timer_serial.timeout.connect(self.update_serial)
        self.timer_song.timeout.connect(self.update_song)

        # Loading settings and songs
        self.config: configparser.ConfigParser = configparser.ConfigParser()
        self.load_settings()
        self.load_songs()

        self.show()

    def load_settings(self) -> None:
        '''Loads settings from custom or default config file and applies them.'''
        # TODO Check if init file exists
        self.config.read_file(codecs.open("data/default.ini", "r", "utf8"))
        # if there is custom config file it overwrites default settings
        if os.path.exists('config.ini'):
            self.config.read_file(codecs.open("config.ini", "r", "utf8"))
            l.info('Loaded custom config file.')

        # Loading settings to variables.
        self.songs_directory: str = str(
            self.config['Settings']['songs_directory'])

        self.serial_port: str = str(
            self.config['Settings']['serial_port'])

        self.use_spotify: bool = bool(
            self.config['Settings']['use_spotify'])

        self.playback_time: int = int(
            self.config['Rules']['playback_time'])

        self.points_correct: int = int(
            self.config['Rules']['points_correct'])

        self.points_incorrect: int = int(
            self.config['Rules']['points_incorrect'])

        for i, name in enumerate(self.config['Team Names'].values()):
            self.label_team_names[i].setText(str(name))
        
        self.number_teams: int = int(self.config['Rules']['number_teams'])
        # Disabling unused team labels
        for i in range(self.number_teams, 6):
            self.widget_team[i].hide()

        self.use_spotify: bool = self.config['Settings'].getboolean('use_spotify')

        if self.use_spotify:
            scope = 'user-read-playback-state user-modify-playback-state user-read-currently-playing app-remote-control'
            self.spotify_cache: CacheFileHandler = CacheFileHandler(
                cache_path=os.path.join(os.getcwd(), 'cache/.spotify_cache')
            )
            self.spotify_oauth: SpotifyOAuth = SpotifyOAuth(
                client_id=self.config['Settings']['spotify_client_id'],
                client_secret=self.config['Settings']['spotify_client_secret'],
                redirect_uri=self.config['Settings']['spotify_redirect_uri'],
                scope=scope,
                open_browser=False,
                cache_handler=self.spotify_cache
            )
            if not self.spotify_oauth.validate_token(self.spotify_cache.get_cached_token()):
                url: QUrl = QUrl(self.spotify_oauth.get_authorize_url())
                dialog: QDialog = BrowserDialog(self, url)
                dialog.exec_()
                response_url: str = dialog.browser.url().toString()
                code: str = self.spotify_oauth.parse_response_code(response_url)
                self.spotify_oauth.get_access_token(code, as_dict=False)
            self.spotify: Spotify = Spotify(oauth_manager=self.spotify_oauth)
            try:
                self.spotify.pause_playback()
            except Exception as e:
                print(e)

    def load_songs(self) -> None:
        '''Loads songs and shuffles them automatically.'''
        # Check if song dir is selected and if its real
        if not self.use_spotify:
            if self.songs_directory and os.path.exists(self.songs_directory):
                # Clear and create new songs list
                self.loaded_songs: list = []
                for file in os.listdir(self.songs_directory):
                    if file.endswith('.mp3') or file.endswith('.wav'):
                        self.loaded_songs.append(
                            {
                                'path': os.path.join(self.songs_directory, file),
                                'name': file[:-4],
                                'extension': file[-3:]
                            }
                        )
                random.shuffle(self.loaded_songs)
                l.info(f'Loaded {len(self.loaded_songs)} songs')

    def team_pressed(self, n: int) -> None:
        if not self.is_team_guessing:
            if self.playback_state == self.S_PLAYING:
                # Pausing playback of the song only if song is playing.
                self.pause_playback()

            self.is_team_guessing = True
            self.guessing_team = n

            # Updating visuals.
            team_name = list(self.config['Team Names'].values())[n]
            self.label_team.setText(team_name)
            self.button_yes.setEnabled(True)
            self.button_no.setEnabled(True)
            self.button_next.setEnabled(False)
            self.button_pause_resume.setEnabled(False)

    def update_serial(self) -> None:
        # TODO Read incoming serial data and put it into queue.
        return

    def update_song(self) -> None:
        '''Updates progress bar and checks if song should be stopped.'''
        self.millis += 1
        seconds: int = int((self.millis/1000) % 60)
        minutes: int = int((self.millis/(1000*60)) % 60)
        text: str = f'{minutes:02d}:{seconds:02d}'
        value: int = int(self.millis/self.playback_time/10)

        self.label_timer.setText(text)
        self.progress_bar.setValue(value)

        if self.millis >= self.playback_time*1000:
            self.stop_playback()

    def open_settings(self) -> None:
        '''Opens dialog for selecting settings.'''
        l.info('Settings dialog opened.')
        dialog: QDialog = SettingsDialog(self)
        dialog.exec_()
        l.info('Settings dialog closed.')
        self.load_songs()

    def next_playback(self) -> None:
        if self.use_spotify:
            try:
                self.spotify.next_track()
                QtTest.QTest.qWait(200)
                response = self.spotify.currently_playing()
                name = response['item']['name']
                artists = ''
                for artist in response['item']['artists']:
                    if artists:
                        artists += ', '
                    artists += str(artist['name'])
                print(name, artists)

                self.current_song = song = {'name': name, 'arists': artists}
                self.millis = 0
                self.playback_state = self.S_PLAYING

                # Updating visuals
                self.progress_bar.setValue(0)
                self.label_title.setText(song['name'])
                self.label_artist.setText(song['arists'])
                self.label_team.setText('')
                self.button_next.setEnabled(False)
                self.button_pause_resume.setEnabled(True)
                self.button_pause_resume.setText('Pause')

                # Starting song timer
                self.timer_song.start(1)

            except Exception as e:
                print(e)
        else:
            if self.loaded_songs:
                song = self.loaded_songs.pop()

                # Defining song frequency to playback at right speed
                freq = 44100
                if song['extension'] == 'mp3':
                    file = mp3.MP3(song['path'])
                    freq = file.info.sample_rate
                elif song['extension'] == 'wav':
                    file = wave.open(song['path'])
                    freq = file.getframerate()

                # Setting right frequency and starting playback
                mixer.quit()
                mixer.init(frequency=freq)
                mixer.music.load(song['path'])
                mixer.music.play()

                # Updating some variables
                self.current_song = song
                self.millis = 0
                self.playback_state = self.S_PLAYING

                # Updating visuals
                self.progress_bar.setValue(0)
                self.label_title.setText(song['name'])
                self.label_artist.setText('')
                self.label_team.setText('')
                self.button_next.setEnabled(False)
                self.button_pause_resume.setEnabled(True)
                self.button_pause_resume.setText('Pause')

                # Starting song timer
                self.timer_song.start(1)

                l.info('Started playback.')
            else:
                # TODO Display warning dialog.
                l.warning('No songs loaded!')


    def pause_resume(self) -> None:
        if self.playback_state == self.S_PLAYING:
            self.pause_playback()
        elif self.playback_state == self.S_PAUSED:
            self.resume_playback()

        
    def pause_playback(self) -> None:
        if self.playback_state == self.S_PLAYING:
            # Pausing playback and timer
            if self.use_spotify:
                try:
                    self.spotify.pause_playback()
                except Exception as e:
                    print(e)
            else:
                mixer.music.pause()
            
            self.timer_song.stop()

            # Updating playback state
            self.playback_state = self.S_PAUSED

            # Updating visuals
            self.button_next.setEnabled(True)
            self.button_pause_resume.setText('Resume')
        else:
            l.warning('Song is not playing.')

    def stop_playback(self) -> None:
        if self.playback_state == self.S_PLAYING:
            # Stopping playback and timer
            if self.use_spotify:
                try:
                    self.spotify.pause_playback()
                except Exception as e:
                    print(e)
            else:
                mixer.music.stop()
            
            self.timer_song.stop()

            # Updating playback state
            self.playback_state = self.S_STOPPED

            # Updating visuals
            self.button_next.setEnabled(True)
            self.button_pause_resume.setEnabled(False)
        else:
            l.warning('Song is not playing.')

    def resume_playback(self) -> None:
        if self.playback_state == self.S_PAUSED:
            # Resuming playback and timer
            if self.use_spotify:
                try:
                    self.spotify.start_playback()
                except Exception as e:
                    print(e)
            else:
                mixer.music.unpause()

            self.timer_song.start(1)

            # Updating playback state.
            self.playback_state = self.S_PLAYING

            # Updating visuals
            self.button_next.setEnabled(False)
            self.button_pause_resume.setText('Pause')
        else:
            l.warning('Song is already playing.')

    def answer_correct(self) -> None:
        if self.is_team_guessing:
            # Changing score of team
            team: int = self.guessing_team
            self.team_scores[team] += self.points_correct
            self.label_team_scores[team].setText(str(self.team_scores[team]))

            self.is_team_guessing = False

            # Updating visuals
            self.button_no.setEnabled(False)
            self.button_yes.setEnabled(False)
            self.button_next.setEnabled(True)
            self.button_pause_resume.setEnabled(False)

    def answer_incorrect(self) -> None:
        if self.is_team_guessing:
            # Changing score of team
            team: int = self.guessing_team
            self.team_scores[team] += self.points_incorrect
            self.label_team_scores[team].setText(str(self.team_scores[team]))

            self.is_team_guessing = False

            # Updating visuals
            self.button_no.setEnabled(False)
            self.button_yes.setEnabled(False)
            self.button_next.setEnabled(True)
            if self.playback_state == self.S_PAUSED:
                self.button_pause_resume.setEnabled(True)

    def closeEvent(self, event) -> None:
        self.config['Settings']['songs_directory'] = str(
            self.songs_directory)
        self.config['Settings']['serial_port'] = str(self.serial_port)

        self.config['Rules']['playback_time'] = str(self.playback_time)

        with open('config.ini', 'w', encoding='UTF-8') as file:
            self.config.write(file)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        '''Handling keypresses'''
        if e.key() - Qt.Key.Key_1 in range(self.number_teams):
            self.team_pressed(e.key() - Qt.Key.Key_1)

        # if e.key() == Qt.Key.Key_Space:
        #     self.pause_resume( )
   


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__()
        uic.loadUi('data/settings.ui', self)

        self.parent: Ui = parent

        # Loading widgets
        self.button_refresh: QPushButton = self.findChild(
            QPushButton, 'b_refresh')
        self.button_connect: QPushButton = self.findChild(
            QPushButton, 'b_connect')
        self.button_save: QPushButton = self.findChild(QPushButton, 'b_exit')
        self.button_directory: QToolButton = self.findChild(
            QToolButton, 'b_directory')
        self.combobox_port: QComboBox = self.findChild(QComboBox, 'c_box')
        self.input_songs_dir: QLineEdit = self.findChild(QLineEdit, 'le_songs')
        self.input_playback_time: QLineEdit = self.findChild(
            QLineEdit, 'le_playback')
        self.slider_playback_time: QSlider = self.findChild(
            QSlider, 's_playback')

        # Attaching functions to widgets
        self.button_refresh.clicked.connect(self.update_ports)
        self.button_connect.clicked.connect(self.connect_serial)
        self.button_save.clicked.connect(self.save_exit)
        self.button_directory.clicked.connect(self.open_directory)
        # self.combobox_port.activated.connect(self.update_port)
        self.input_songs_dir.returnPressed.connect(self.update_songs_dir)
        self.input_songs_dir.editingFinished.connect(self.update_songs_dir)
        self.slider_playback_time.valueChanged.connect(
            self.update_playback_time)

        self.input_songs_dir.setText(self.parent.songs_directory)
        self.slider_playback_time.setValue(self.parent.playback_time)

        self.update_ports(True)

    def update_ports(self, get_from_parent: bool = False) -> None:
        ports = [port.device for port in list_ports.comports()]
        ports.sort()

        self.combobox_port.clear()

        if get_from_parent and self.parent.serial_port in ports:
            self.combobox_port.addItem(self.parent.serial_port)
        else:
            self.combobox_port.addItems(ports)
            self.button_connect.setEnabled(True)

    def connect_serial(self) -> None:
        # TODO Opens serial connection to selected port.
        return

    def save_exit(self) -> None:
        self.parent.playback_time = self.slider_playback_time.value()
        self.parent.songs_directory = self.input_songs_dir.text()
        self.close()

    def open_directory(self) -> None:
        directory: str = str(
            QFileDialog.getExistingDirectory(self, 'Select Directory'))
        self.input_songs_dir.setText(directory)

    def update_songs_dir(self) -> None:
        directory: str = self.input_songs_dir.text()
        if not os.path.exists(directory):
            self.input_songs_dir.clear()

    def update_playback_time(self) -> None:
        value: int = self.slider_playback_time.value()
        self.input_playback_time.setText(str(value))

    def closeEvent(self, event) -> None:
        self.save_exit()


class BrowserDialog(QDialog):
    def __init__(self, parent: Ui, link: QUrl):
        super().__init__()

        self.parent: Ui = parent

        self.setMinimumSize(500, 1000)
        self.setWindowTitle('Login to Spotify')

        self.browser: QWebEngineView = QWebEngineView()
        self.browser.page().profile().cookieStore().deleteAllCookies()
        self.browser.setUrl(link)
        self.browser.urlChanged.connect(self.url_check)

        self.layout: QVBoxLayout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.browser)

        self.setLayout(self.layout)

        self.show()

    def url_check(self):
        url = str(self.browser.url())
        if self.parent.config['Settings']['spotify_redirect_uri'] in url:
            self.accept()
        


app = QApplication(sys.argv)

_font_id = QFontDatabase.addApplicationFont(
    os.path.join(os.getcwd(), "data/Manrope-Regular.ttf"))
_fontstr = QFontDatabase.applicationFontFamilies(_font_id)[0]
_font = QFont(_fontstr, 8)
app.setFont(_font)

window = Ui()

app.exec_()
