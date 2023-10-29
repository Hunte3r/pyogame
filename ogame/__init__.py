import re
import requests
import unittest
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import json
import math
import random
import time
import os

# Blackbox
import base64
from random import randint
from urllib.parse import quote

# Captcha
import io
from PIL import Image
import imagehash
import cv2
import shutil
from pytesseract import image_to_string

try:
    import constants as const
except ImportError:
    import ogame.constants as const

user_agent_raw = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'


class OGame(object):
    def __init__(
            self,
            universe,
            username,
            password,
            is_pioneer=False,
            token=None, proxy='',
            language=None, server_number=None, blackbox_token=None
    ):
        self.universe = universe
        self.username = username
        self.password = password
        self.proxy = proxy
        self.language = language
        self.server_number = server_number
        self.is_pioneer = is_pioneer
        self.session = requests.Session()
        self.session.proxies.update({'https': self.proxy})
        self.token = token
        self.blackbox_token = blackbox_token
        self.user_agent_raw = user_agent_raw
        self.user_agent = {
            'User-Agent': f'{self.user_agent_raw}'
        }
        self.session.headers.update(self.user_agent)

        try:
            if token is None:
                print("Login without Token")
                self.login()
            else:
                print("Login with Token")
                self.session.headers.update(
                    {'authorization': f'Bearer {token}'}
                )
                self.set_cookies_and_accounts()

            self.get_server_number_and_language()

            self.set_server_id()

            self.index_php = f'https://s{self.server_number}-{self.language}.ogame.gameforge.com/game/index.php?'

            self.blackbox_token = get_blackbox()

            self.set_headers_and_cookies()

            params = {
                "id": self.server_id,
                "server": {
                    "language": self.language,
                    "number": self.server_number
                },
                "clickedButton": "quick_join",
                "blackbox": f"tra:{self.blackbox_token}"
            }

            login_url = self.get_login_link(params)

            self.landing_page = self.session.get(login_url).text

            self.landing_page = self.session.get(
                self.index_php + 'page=ingame'
            ).text

            self.landing_page = BeautifulSoup4(self.landing_page)

            self.player = self.landing_page.find(
                'meta', {'name': 'ogame-player-name'}
            )['content']
            self.player_id = int(self.landing_page.find(
                'meta', {'name': 'ogame-player-id'}
            )['content'])

            print(f'Player ID: {self.player_id}')

            del self.session.headers['authorization']
        except Exception as e:
            print(e)

    def login(self):

        try:
            self.session.get('https://lobby.ogame.gameforge.com/')
            self.blackbox_token = get_blackbox()
            login_data = self._build_login_data()

            response = self.session.post(
                'https://gameforge.com/api/v1/auth/thin/sessions',
                json=login_data
            )

            if response.status_code == 409:
                self._handle_captcha(response)
            elif response.status_code == 201:
                print(f'Login ok')
            else:
                print(f'DEBUG error code: {response.status_code}')
                raise ValueError(f"Unexpected response status code: {response.status_code} {response.text}")

            self._handle_login_success(response)

        except Exception as e:
            print(f'error: {e}')
            raise

    def _build_login_data(self):
        game_environment_id = '0a31d605-ffaf-43e7-aa02-d06df7116fc8'
        platform_game_id = '1dfd8e7e-6e1a-4eb1-8c64-03c3b62efd2f'

        if self.is_pioneer:
            game_environment_id = '1dfd8e7e-6e1a-4eb1-8c64-03c3b62efd2f'
            platform_game_id = 'b990cab3-3573-4605-965a-0693c0adde26'

        return {
            'identity': self.username,
            'password': self.password,
            'locale': 'de_DE',
            'gfLang': self.language,
            'platformGameId': platform_game_id,
            'gameEnvironmentId': game_environment_id,
            'autoGameAccountCreation': False,
            'blackbox': 'tra:{}'.format(self.blackbox_token)
        }

    def _handle_captcha(self, response):

        gfchallengeid = response.headers['gf-challenge-id'].replace(';https://challenge.gameforge.com', '')

        response2 = self.session.get(
            url='https://challenge.gameforge.com/challenge/' + gfchallengeid
        )

        response3 = self.session.get(
            url='https://image-drop-challenge.gameforge.com/challenge/' + gfchallengeid + '/en-GB'
        ).json()

        lastupdated = response3['lastUpdated']

        captcha_required = True
        while captcha_required:

            response4 = self.session.get(
                url='https://image-drop-challenge.gameforge.com/challenge/'
                    + gfchallengeid
                    + '/en-GB/text?'
                    + str(lastupdated)
            )

            challenge_text = response4.content

            response5 = self.session.get(
                url='https://image-drop-challenge.gameforge.com/challenge/'
                    + gfchallengeid
                    + '/en-GB/drag-icons?'
                    + str(lastupdated)
            )

            challenge_icons = response5.content

            response6 = self.session.get(
                url='https://image-drop-challenge.gameforge.com/challenge/'
                    + gfchallengeid
                    + '/en-GB/drop-target?'
                    + str(lastupdated)
            )

            answer = solve_captcha(challenge_text, challenge_icons)

            payload7 = {
                'answer': int(answer)
            }

            # Post answer
            response7 = self.session.post(
                url='https://image-drop-challenge.gameforge.com/challenge/'
                    + gfchallengeid
                    + '/en-GB',
                json=payload7
            ).json()

            if response7['status'] == 'presented':
                print('next captcha required')
                lastupdated = response7['lastUpdated']
            elif response7['status'] == 'solved':
                captcha_required = False

        self.login()

    def _handle_login_success(self, response):
        self.token = response.json()['token']
        with open(os.path.abspath(os.path.join(os.getcwd(), 'bearer_token.txt')), 'w') as f_token:
            f_token.write(self.token)
        self.session.headers.update(
            {'authorization': 'Bearer {}'.format(self.token)}
        )

        # Set the cookies
        cookies = {
            "gf-token-production": "{}".format(self.token)
        }

        self.session.cookies.update(cookies)

    def set_cookies_and_accounts(self):
        # Update the session headers with the token
        self.session.headers.update(
            {'authorization': f'Bearer {self.token}'}
        )

        # Set the cookies
        cookies = {
            "gf-token-production": f"{self.token}"
        }
        self.session.cookies.update(cookies)

        # Get the accounts
        if self.is_pioneer == 1:
            accounts = self.session.get(
                url='https://lobby-pioneers.ogame.gameforge.com/api/users/me/accounts'
            ).json()
        else:
            accounts = self.session.get(
                url='https://lobby.ogame.gameforge.com/api/users/me/accounts'
            ).json()

        # Set the language from the first account if not already set
        if self.language is None:
            self.language = accounts[0]['server']['language']

        # If there's an error in the accounts, remove the authorization header and call the login function
        if 'error' in accounts:
            del self.session.headers['authorization']
            self.login()

    def get_server_number_and_language(self):
        # Get the server list
        if self.is_pioneer == 1:
            servers = self.session.get(
                url='https://lobby-pioneers.ogame.gameforge.com/api/servers'
            ).json()
        else:
            servers = self.session.get(
                url='https://lobby.ogame.gameforge.com/api/servers'
            ).json()

        # Find the matching server and set the server_number and language
        for server in servers:
            if server['name'] == self.universe and self.is_pioneer == 1:
                self.server_number = server['number']
                self.language = server['language']
                break
            elif server['name'] == self.universe:
                self.server_number = server['number']
                if self.language is None:
                    self.language = server['language']
                break
            elif server['name'] == self.universe and self.language is None:
                self.server_number = server['number']
                break

        # Check if the server_number was found, otherwise raise an error
        if self.server_number is None:
            raise ValueError("Universe not found")

    def set_server_id(self):
        # Get the accounts
        if self.is_pioneer == 1:
            accounts = self.session.get(
                url='https://lobby-pioneers.ogame.gameforge.com/api/users/me/accounts'
            ).json()
        else:
            accounts = self.session.get(
                url='https://lobby.ogame.gameforge.com/api/users/me/accounts'
            ).json()

        # Find the matching account and set the server_id
        for account in accounts:
            if account['server']['number'] == self.server_number and account['server']['language'] == self.language:
                self.server_id = account['id']
                break
            elif account['server']['number'] == self.server_number and self.language is None:
                self.server_id = account['id']
                self.language = account['server']['language']
                break
            else:
                pass

        if self.server_id is None:
            raise ValueError("Account not found for the specified server and language.")

    def set_headers_and_cookies(self):
        # Set the headers
        self.session.headers.update(
            {
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/json',
            }
        )

        # Set the cookies
        cookies = {
            "gf-token-production": f"{self.token}"
        }

        self.session.cookies.update(cookies)

    def get_login_link(self, params):
        if self.is_pioneer == 1:
            login_link = self.session.post(
                url="https://lobby-pioneers.ogame.gameforge.com/api/users/me/loginLink",
                json=params
            )
        else:
            login_link = self.session.post(
                url="https://lobby.ogame.gameforge.com/api/users/me/loginLink",
                json=params
            )

        login_link = login_link.json()

        if len(login_link) < 1:
            raise ValueError('No LoginLink!')

        return login_link['url']

    def test(self):
        import ogame.test
        ogame.test.UnittestOgame.empire = self
        suite = unittest.TestLoader().loadTestsFromModule(ogame.test)
        return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

    def server(self):
        class Server:
            version = self.landing_page.find('meta', {'name': 'ogame-version'})

            class Speed:
                universe = self.landing_page.find(
                    'meta', {'name': 'ogame-universe-speed'}
                )
                universe = int(universe['content'])
                fleet = self.landing_page.find(
                    'meta', {'name': 'ogame-universe-speed-fleet-peaceful'}
                )
                fleet = int(fleet['content'])

            class Donut:
                galaxy = self.landing_page.find(
                    'meta', {'name': 'ogame-donut-galaxy'}
                )['content']
                if 1 == int(galaxy):
                    galaxy = True
                else:
                    galaxy = False
                system = self.landing_page.find(
                    'meta', {'name': 'ogame-donut-system'}
                )['content']
                if 1 == int(system):
                    system = True
                else:
                    system = False

        return Server

    def attacked(self):
        response = self.session.get(
            url=self.index_php + 'page=componentOnly'
                                 '&component=eventList&action=fetchEventBox&ajax=1&asJson=1',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        if 0 < response['hostile']:
            return True
        else:
            return False

    def neutral(self):
        response = self.session.get(
            url=self.index_php + 'page=componentOnly'
                                 '&component=eventList&action=fetchEventBox&ajax=1&asJson=1',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        if 0 < response['neutral']:
            return True
        else:
            return False

    def friendly(self):
        response = self.session.get(
            url=self.index_php + 'page=componentOnly'
                                 '&component=eventList&action=fetchEventBox&ajax=1&asJson=1',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        if 0 < response['friendly']:
            return True
        else:
            return False

    def highscore(self, page=1):
        data = {
            'page': 'highscoreContent',
            'category': '1',
            'type': '0',
            'site': str(page)
        }
        response = self.session.post(
            url=self.index_php,
            params=data,
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        bs4 = BeautifulSoup4(response.content)
        player_list = []
        for i in range(1, 101):
            rawy = bs4.select('tr', attrs={'class': ''})[i]

            class PlayerData:
                name = rawy.find('span', attrs={'class': 'playername'}).text.strip()
                player_id = int(rawy['id'].replace("position", ""))
                rank = int(rawy.find('td', attrs={'class': 'position'}).text.strip())
                points = int(rawy.find('td', attrs={'class': 'score'}).text.strip().replace(".", "").replace(",", ""))
                list = [
                    name, player_id, rank, points
                ]

            player_list.append(PlayerData)
        return player_list

    def character_class(self):
        character = self.landing_page.find_partial(
            class_='sprite characterclass medium')
        return character['class'][3]

    def choose_character_class(self, classid):  # "1"-miner # "2"-warrior # "3"-explorer
        character = self.landing_page.find_partial(
            class_='sprite characterclass medium')
        data = {
            'page': "ingame",
            'component': "characterclassselection",
            'characterClassId': classid,
            'action': "selectClass",
            'ajax': '1',
            'asJson': '1'
        }
        if character['class'][3] == 'none':
            response = self.session.post(
                url=self.index_php,
                params=data,
                headers={'X-Requested-With': 'XMLHttpRequest'}
            ).json()
            if response['status'] == 'success':
                return True
        return False

    def lf_character_class(self, planet_id):
        response_class = self.session.get(
            url=self.index_php + 'page=ingame&component=overview',
            params={'cp': planet_id}
        ).text
        response_class = BeautifulSoup4(response_class)
        lf_character_class = response_class.find_partial(
            class_='lifeform-item-icon small')
        if lf_character_class:
            return lf_character_class['class'][2]
        else:
            return None

    def rank(self):
        rank = self.landing_page.find(id='bar')
        rank = rank.find_all('li')[1].text
        rank = re.search(r'\((.*)\)', rank).group(1)
        return int(rank)

    def planet_ids(self):
        ids = []
        for celestial in self.landing_page.find_all(class_='smallplanet'):
            ids.append(int(celestial['id'].replace('planet-', '')))
        return ids

    def planet_names(self):
        return [planet.text for planet in
                self.landing_page.find_all(class_='planet-name')]

    def id_by_planet_name(self, name):
        for planet_name, id in zip(
                OGame.planet_names(self), OGame.planet_ids(self)
        ):
            if planet_name == name:
                return id

    def name_by_planet_id(self, id):
        for _id, planet_name in zip(
                OGame.planet_ids(self), OGame.planet_names(self)
        ):
            if id == _id:
                return planet_name

    def moon_ids(self):
        moons = []
        for moon in self.landing_page.find_all(class_='moonlink'):
            moon = moon['href']
            moon = re.search('cp=(.*)', moon).group(1)
            moons.append(int(moon))
        return moons

    def moon_names(self):
        names = []
        for name in self.landing_page.find_all(class_='moonlink'):
            name = name['title']
            names.append(re.search(r'<b>(.*) \[', name).group(1))
        return names

    def slot_celestial(self):
        class Slot:
            planets = self.landing_page.find(
                'p',
                attrs={'class': 'textCenter'}
            ).find('span').text.split('/')
            planets = [int(planet) for planet in planets]
            free = planets[1] - planets[0]
            total = planets[1]

        return Slot

    def celestial(self, id):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=overview',
            params={'cp': id}
        ).text
        textContent1 = re.search(
            r'textContent\[1] = "(.*)km \(<span>(.*)<(.*)<span>(.*)<',
            response
        )
        textContent3 = re.search(
            r'textContent\[3] = "(.*)"',
            response
        )
        textContent3 = textContent3.group(1).replace('\\u00b0', '')
        textContent3 = re.findall(r'\d+(?: \d+)?', textContent3)

        class Celestial:
            diameter = int(textContent1.group(1).replace('.', ''))
            used = int(textContent1.group(2))
            total = int(textContent1.group(4))
            free = total - used
            temperature = [
                textContent3[0],
                textContent3[1]
            ]
            coordinates = OGame.celestial_coordinates(self, id)

        return Celestial

    def celestial_queue(self, id):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=overview',
            params={'cp': id}
        ).text
        research_time = re.search(r'var restTimeresearch = ([0-9]+)', response)
        if research_time is None:
            research_time = datetime.fromtimestamp(0)
        else:
            research_time = int(research_time.group(1))
            research_time = datetime.fromtimestamp(research_time)
        build_time = re.search(r'var restTimebuilding = ([0-9]+)', response)
        if build_time is None:
            build_time = datetime.fromtimestamp(0)
        else:
            build_time = int(build_time.group(1))
            build_time = datetime.fromtimestamp(build_time)
        shipyard_time = re.search(r'var restTimeship2 = ([0-9]+)', response)
        if shipyard_time is None:
            shipyard_time = datetime.fromtimestamp(0)
        else:
            shipyard_time = int(shipyard_time.group(1))
            shipyard_time = datetime.now() + timedelta(seconds=shipyard_time)

        class Queue:
            research = research_time
            buildings = build_time
            shipyard = shipyard_time
            list = [
                research,
                buildings,
                shipyard
            ]

        return Queue

    def celestial_coordinates(self, id):
        for celestial in self.landing_page.find_all(class_='smallplanet'):
            planet = celestial.find(class_='planetlink')
            if str(id) in planet['href']:
                coordinates = re.search(r'\[(.*)]', planet['title']).group(1)
                coordinates = [int(coords) for coords in coordinates.split(':')]
                coordinates.append(const.destination.planet)
                return coordinates
            moon = celestial.find(class_='moonlink')
            if moon and str(id) in moon['href']:
                coordinates = re.search(r'\[(.*)]', moon['title']).group(1)
                coordinates = [int(coords) for coords in coordinates.split(':')]
                coordinates.append(const.destination.moon)
                return coordinates

    def resources(self, id):
        response = self.session.get(
            self.index_php + 'page=resourceSettings&cp={}'.format(id)
        ).text
        bs4 = BeautifulSoup4(response)

        def to_int(string):
            return int(float(string.replace('M', '000').replace('n', '')))

        class Resources:
            resources = [bs4.find(id='resources_metal')['data-raw'],
                         bs4.find(id='resources_crystal')['data-raw'],
                         bs4.find(id='resources_deuterium')['data-raw']]
            resources = [to_int(resource) for resource in resources]
            metal = resources[0]
            crystal = resources[1]
            deuterium = resources[2]
            day_production = bs4.find(
                'tr',
                attrs={'class': 'summary'}
            ).find_all(
                'td',
                attrs={'class': 'undermark'}
            )
            day_production = [
                int(day_production[0].span['title'].replace('.', '')),
                int(day_production[1].span['title'].replace('.', '')),
                int(day_production[2].span['title'].replace('.', ''))
            ]
            storage = bs4.find_all('tr')
            for stor in storage:
                if len(stor.find_all('td', attrs={'class': 'left2'})) != 0:
                    storage = stor.find_all('td', attrs={'class': 'left2'})
                    break
            storage = [
                int(storage[0].span['title'].replace('.', '')),
                int(storage[1].span['title'].replace('.', '')),
                int(storage[2].span['title'].replace('.', ''))
            ]
            darkmatter = to_int(bs4.find(id='resources_darkmatter')['data-raw'])
            energy = to_int(bs4.find(id='resources_energy')['data-raw'])

        return Resources

    def resources_settings(self, planet_id, settings=None):
        response = self.session.get(
            self.index_php + 'page=ingame&component=resourcesettings&cp={}'.format(planet_id)
        ).text
        bs4 = BeautifulSoup4(response)
        settings_form = {
            'saveSettings': 1,
        }
        token = re.search(r'var token\s?=\s?"([^"]*)";', response).group(1)
        settings_form.update({'token': token})
        names = [
            '1', '2', '3', '4', '12', '212', '217'
        ]
        for building_name in names:
            select = bs4.find('select', {'name': 'productionFactor[{}]'.format(building_name)})
            selected_value = select.find('option', selected=True)['value']
            settings_form.update({building_name: selected_value})
        if settings is not None:
            for building, speed in settings.items():
                settings_form.update(
                    {'last{}'.format(building[0]): speed * 10}
                )
            self.session.post(
                self.index_php + 'page=resourceSettings&cp={}'.format(id),
                data=settings_form
            )
        settings_data = {}
        for key, value in settings_form.items():
            if key in names:
                building_id = int(key.replace('last', ''))
                building_name = const.buildings.building_name(
                    (building_id, 1, 'supplies')
                )
                settings_data[building_name] = value

        class Settings:
            metal_mine = settings_data['metal_mine']
            crystal_mine = settings_data['crystal_mine']
            deuterium_mine = settings_data['deuterium_mine']
            solar_plant = settings_data['solar_plant']
            fusion_plant = settings_data['fusion_plant']
            solar_satellite = settings_data['solar_satellite']
            crawler = settings_data['crawler']
            list = [
                metal_mine, crystal_mine, deuterium_mine,
                solar_plant, fusion_plant, solar_satellite,
                crawler
            ]

        return Settings

    def isPossible(self: str):
        if self == 'on':
            return True
        else:
            return False

    def inConstruction(self):
        if self == 'active':
            return True
        else:
            return False

    def supply(self, id):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=supplies&cp={}'
            .format(id)
        ).text
        bs4 = BeautifulSoup4(response)
        levels = [
            int(level['data-value'])
            for level in bs4.find_all('span', {'data-value': True})
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Supply:
            def __init__(self, i):
                self.level = levels[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Supplies(object):
            metal_mine = Supply(0)
            crystal_mine = Supply(1)
            deuterium_mine = Supply(2)
            solar_plant = Supply(3)
            fusion_plant = Supply(4)
            metal_storage = Supply(7)
            crystal_storage = Supply(8)
            deuterium_storage = Supply(9)

        return Supplies

    def facilities(self, id):
        response = self.session.get(
            self.index_php + 'page=ingame&component=facilities&cp={}'
            .format(id)
        ).text
        bs4 = BeautifulSoup4(response)
        levels = [
            int(level['data-value'])
            for level in bs4.find_all(
                'span', {'class': 'level', 'data-value': True}
            )
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Facility:
            def __init__(self, i):
                self.level = levels[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Facilities(object):
            robotics_factory = Facility(0)
            shipyard = Facility(1)
            research_laboratory = Facility(2)
            alliance_depot = Facility(3)
            missile_silo = Facility(4)
            nanite_factory = Facility(5)
            terraformer = Facility(6)
            repair_dock = Facility(7)

        return Facilities

    def moon_facilities(self, id):
        response = self.session.get(
            url='{}page=ingame&component=facilities&cp={}'
            .format(self.index_php, id)
        ).text
        bs4 = BeautifulSoup4(response)
        levels = [
            int(level['data-value'])
            for level in bs4.find_all(class_=['targetlevel', 'level']) if level.get('data-value')
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Facility:
            def __init__(self, i):
                self.level = levels[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Facilities(object):
            robotics_factory = Facility(0)
            shipyard = Facility(1)
            moon_base = Facility(2)
            sensor_phalanx = Facility(3)
            jump_gate = Facility(4)

        return Facilities

    def traider(self, id):
        raise NotImplementedError("function not implemented yet PLS contribute")

    def research(self, id=None):
        if id is None:
            id = self.planet_ids()[0]
        response = self.session.get(
            url=self.index_php,
            params={'page': 'ingame', 'component': 'research',
                    'cp': id}
        ).text
        bs4 = BeautifulSoup4(response)
        levels = [
            int(level['data-value'])
            for level in bs4.find_all(
                'span', {'class': 'level', 'data-value': True}
            )
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Research:
            def __init__(self, i):
                self.level = levels[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Researches(object):
            energy = Research(0)
            laser = Research(1)
            ion = Research(2)
            hyperspace = Research(3)
            plasma = Research(4)
            combustion_drive = Research(5)
            impulse_drive = Research(6)
            hyperspace_drive = Research(7)
            espionage = Research(8)
            computer = Research(9)
            astrophysics = Research(10)
            research_network = Research(11)
            graviton = Research(12)
            weapons = Research(13)
            shielding = Research(14)
            armor = Research(15)

        return Researches

    def ships(self, id):
        response = self.session.get(
            self.index_php + 'page=ingame&component=shipyard&cp={}'
            .format(id)
        ).text
        bs4 = BeautifulSoup4(response)
        ships_amount = [
            int(level['data-value'])
            for level in bs4.find_all(class_='amount')
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Ship:
            def __init__(self, i):
                self.amount = ships_amount[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Crawler:
            if id not in OGame.moon_ids(self):
                amount = ships_amount[16]
                self.is_possible = OGame.isPossible(technologyStatus[16])
                self.in_construction = OGame.inConstruction(
                    technologyStatus[16]
                )
            else:
                amount = 0
                is_possible = False
                in_construction = False

        class Ships(object):
            light_fighter = Ship(0)
            heavy_fighter = Ship(1)
            cruiser = Ship(2)
            battleship = Ship(3)
            interceptor = Ship(4)
            bomber = Ship(5)
            destroyer = Ship(6)
            deathstar = Ship(7)
            reaper = Ship(8)
            explorer = Ship(9)
            small_transporter = Ship(10)
            large_transporter = Ship(11)
            colonyShip = Ship(12)
            recycler = Ship(13)
            espionage_probe = Ship(14)
            solarSatellite = Ship(15)
            crawler = Crawler

        return Ships

    def defences(self, id):
        response = self.session.get(
            self.index_php + 'page=ingame&component=defenses&cp={}'
            .format(id)
        ).text
        bs4 = BeautifulSoup4(response)
        defences_amount = [
            int(level['data-value'])
            for level in bs4.find_all(class_='amount')
        ]
        technologyStatus = [
            status['data-status']
            for status in bs4.find_all('li', {'class': 'technology'})
        ]

        class Defence:
            def __init__(self, i):
                self.amount = defences_amount[i]
                self.is_possible = OGame.isPossible(technologyStatus[i])
                self.in_construction = OGame.inConstruction(technologyStatus[i])

        class Defences(object):
            rocket_launcher = Defence(0)
            laser_cannon_light = Defence(1)
            laser_cannon_heavy = Defence(2)
            gauss_cannon = Defence(3)
            ion_cannon = Defence(4)
            plasma_cannon = Defence(5)
            shield_dome_small = Defence(6)
            shield_dome_large = Defence(7)
            missile_interceptor = Defence(8)
            missile_interplanetary = Defence(9)

        return Defences

    def galaxy(self, coords):
        response = self.session.post(
            url=self.index_php + 'page=ingame&component=galaxyContent&ajax=1',
            data={'galaxy': coords[0], 'system': coords[1]},
            headers={
                'X-Requested-With': 'XMLHttpRequest',
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )

        if response.status_code == 200:
            try:
                response = response.json()
                bs4 = BeautifulSoup4(response['galaxy'])

                def playerId(tag):
                    numbers = re.search(r'[0-9]+', tag).group()
                    return int(numbers)

                players = bs4.find_all_partial(id='player')

                player_names = {
                    playerId(player['id']): player.h1.span.text
                    for player in players
                }

                player_rank = {
                    playerId(player['id']): int(player.a.text)
                    for player in players if player.a.text.isdigit()
                }

                alliances = bs4.find_all_partial(id='alliance')
                alliance_name = {
                    playerId(alliance['id']): alliance.h1.text.strip()
                    for alliance in alliances
                }

                planets = []
                for row in bs4.select('#galaxytable .row'):
                    status = row['class']
                    status.remove('row')
                    if 'empty_filter' in status:
                        continue
                    elif len(status) == 0 and 'administrator' not in str(row).lower():
                        planet_status = [const.status.yourself]
                        pid = self.player_id
                        player_names[pid] = self.player
                    else:
                        planet_status = [
                            re.search('(.*)_filter', sta).group(1)
                            for sta in status
                        ]

                        player = row.find(rel=re.compile(r'player[0-9]+'))
                        if not player:
                            continue
                        pid = playerId(player['rel'][0])
                        if pid == const.status.destroyed:
                            continue

                    planet_timer_row = None
                    if row.find(class_='activity showMinutes tooltip js_hideTipOnMobile') is not None:
                        planet_timer_row = row.find(
                            class_='activity showMinutes tooltip js_hideTipOnMobile').text.strip()
                    elif row.find(class_='activity') is not None:
                        planet_timer_row = '15'
                    else:
                        planet_timer_row = 'None'

                    planet = int(row.find(class_='position').text)
                    planet_cord = const.coordinates(coords[0], coords[1], int(planet))

                    alliance_id = row.find(rel=re.compile(r'alliance[0-9]+'))
                    alliance_id = playerId(
                        alliance_id['rel']) if alliance_id else None

                    debris_resources = [0, 0, 0]
                    try:
                        debris_resources = row.find_all('li', {'class': 'debris-content'})
                        debris_resources = [
                            int(debris_resources[0].text.split(':')[1].replace('.', '')),
                            int(debris_resources[1].text.split(':')[1].replace('.', '')),
                            0
                        ]
                    except:
                        debris_resources = [0, 0, 0]

                    try:
                        recyclers_needed = row.select_one(
                            "div#debris" + str(planet) + " ul.ListLinks li:nth-child(3)").text
                        recyclers_needed = recyclers_needed = int(re.search(r'\d+', recyclers_needed).group())
                    except:
                        recyclers_needed = None

                    planet_id_row = None
                    if row.find('td', {'class': "colonized"}).has_attr('data-planet-id'):
                        planet_id_row = row.find('td', {'class': "colonized"}).attrs['data-planet-id']

                    inactive_row = False
                    if 'inactive_filter' in str(row):
                        inactive_row = True

                    strong_player_row = False
                    if row.find('span', class_='status_abbr_strong') is not None:
                        strong_player_row = True

                    newbie_row = False
                    if row.find(class_='newbie_filter') is not None:
                        newbie_row = True

                    vacation_row = False
                    if 'vacation_filter' in str(row):
                        vacation_row = True

                    honorable_target_row = False
                    if row.find('span', class_='status_abbr_honorableTarget') is not None:
                        honorable_target_row = True

                    administrator_row = False
                    if row.find('span', class_='status_abbr_admin') is not None:
                        administrator_row = True

                    banned_row = False
                    if row.find('span', class_='status_abbr_banned') is not None:
                        banned_row = True

                    is_bandit_row = False
                    if row.find(class_=['rank_bandit1', 'rank_bandit2', 'rank_bandit3']) is not None:
                        is_bandit_row = True

                    is_starlord_row = False
                    if row.find(class_=['rank_starlord1', 'rank_starlord2', 'rank_starlord3']) is not None:
                        is_starlord_row = True

                    is_outlaw_row = False
                    if row.find('span', class_='status_abbr_outlaw') is not None:
                        is_outlaw_row = True

                    # Moon Info
                    moon_id_row = 0
                    if row.find('td', {'class': "moon"}).has_attr('data-moon-id'):
                        moon_id_row = row.find('td', {'class': "moon"}).attrs['data-moon-id']

                    moon_pos = row.find(rel=re.compile(r'moon[0-9]*'))

                    moon_activity_row = 0
                    moon_size_row = 0
                    if int(moon_id_row) > 0:
                        if row.select_one("td.moon div.activity") is not None:
                            moon_activity_row = None
                            if row.find(class_=re.compile(r'alert_triangle')) is not None:
                                moon_activity_row = 15
                            else:
                                moon_activity_row = row.select_one("td.moon div.activity").text.strip()

                        # Moon size
                        moon_size_row = int(row.select_one("td.moon span#moonsize").text.split()[0])

                    debris_16 = bs4.find(class_="expeditionDebrisSlotBox")
                    if debris_16:
                        debris_data = debris_16.find(class_='ListLinks').text.replace(".", "")
                        debris_16 = [int(data) for data in re.findall(r'\d+', debris_data)]
                    else:
                        debris_16 = [0, 0, 0]  # [met, kris, pf]

                    class Position:
                        coordinates = planet_cord
                        galaxy = planet_cord[0]
                        system = planet_cord[1]
                        position = planet_cord[2]
                        planet_name = row.find(id=re.compile(r'planet[0-9]+')).h1.span.text
                        player_name = player_names[pid]
                        player_id = pid
                        rank = player_rank.get(pid)
                        status = planet_status
                        has_moon = moon_pos is not None
                        alliance = alliance_name.get(alliance_id)
                        alli_id = alliance_id
                        planet_activity = planet_timer_row
                        moon_activity = moon_activity_row
                        planet_df = debris_resources[:2]
                        planet_df_m = debris_resources[0]
                        planet_df_c = debris_resources[1]
                        planet_recyclers_needed = recyclers_needed
                        planet_id = planet_id_row
                        moon_size = moon_size_row
                        moon_id = moon_id_row
                        inactive = inactive_row
                        strong_player = strong_player_row
                        newbie = newbie_row
                        vacation = vacation_row
                        honorable_target = honorable_target_row
                        administrator = administrator_row
                        banned = banned_row
                        is_bandit = is_bandit_row
                        is_starlord = is_starlord_row
                        is_outlaw = is_outlaw_row
                        expedition_debris = debris_16[:2]
                        needed_pf = debris_16[2]
                        list = [
                            coordinates, galaxy, system, position, planet_id, planet_name, player_name, player_id, rank,
                            status,
                            has_moon, alliance,
                            planet_activity,
                            moon_activity, planet_df, planet_df_m, planet_df_c, planet_recyclers_needed, moon_size,
                            moon_id, inactive, strong_player, newbie, vacation, honorable_target, administrator, banned,
                            is_bandit, is_starlord, is_outlaw, expedition_debris, needed_pf
                        ]

                    planets.append(Position)

                return planets
            except Exception as galaxy_e:
                print(f'error galaxy: {galaxy_e}')
        else:
            print("error galaxy scan")
            return []

    def galaxy_debris(self, coords):
        response = self.session.post(
            url=self.index_php + 'page=ingame&component=galaxyContent&ajax=1',
            data={'galaxy': coords[0], 'system': coords[1]},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        bs4 = BeautifulSoup4(response['galaxy'])
        debris_fields = []
        debris_rows = bs4.find_all('td', {'class': 'debris'})
        for row in debris_rows:
            debris = True
            row['class'].remove('debris')
            if 'js_no_action' in row['class']:
                debris = False
                row['class'].remove('js_no_action')
            debris_cord = int(row['class'][0].replace('js_debris', ''))
            debris_cord = const.coordinates(
                coords[0],
                coords[1],
                int(debris_cord), const.destination.debris
            )
            debris_resources = [0, 0, 0]
            if debris:
                debris_resources = row.find_all('li', {'class': 'debris-content'})
                debris_resources = [
                    int(debris_resources[0].text.split(':')[1].replace('.', '')),
                    int(debris_resources[1].text.split(':')[1].replace('.', '')),
                    0
                ]

            class Position:
                position = debris_cord
                has_debris = debris
                resources = debris_resources
                metal = resources[0]
                crystal = resources[1]
                deuterium = resources[2]
                list = [
                    position, has_debris, resources,
                    metal, crystal, deuterium
                ]

            if len(coords) >= 3 and coords[2] == Position.position[2]:
                return Position
            debris_fields.append(Position)
        return debris_fields

    def ally(self):
        alliance = self.landing_page.find(name='ogame-alliance-name')
        if alliance:
            return alliance
        else:
            return []

    def officers(self):
        commander_element = self.landing_page.find_partial(class_='on commander')
        admiral_element = self.landing_page.find_partial(class_='on admiral')
        engineer_element = self.landing_page.find_partial(class_='on engineer')
        geologist_element = self.landing_page.find_partial(class_='on geologist')
        technocrat_element = self.landing_page.find_partial(class_='on technocrat')

        class Officers(object):
            commander = commander_element is not None
            admiral = admiral_element is not None
            engineer = engineer_element is not None
            geologist = geologist_element is not None
            technocrat = technocrat_element is not None

        return Officers

    def shop(self):
        raise NotImplementedError("function not implemented yet PLS contribute")

    def shop_items(self):
        raw = self.landing_page.find('head')
        item_list = re.search(r'var itemNames = (.*);', str(raw)).group(1)
        json_list = json.loads(item_list)
        listofelems = [[value, key] for key, value in json_list.items()]
        item_duration = [" 7d", " 30d", " 90d"]
        for count, elem in enumerate(listofelems):
            index = max(count - 1, 0)
            if 87 > count > 1:
                if elem[0] == listofelems[index][0]:
                    if item_duration[0] in listofelems[max(index - 1, 0)][0]:
                        listofelems[index][0] = elem[0] + item_duration[1]
                    else:
                        listofelems[index][0] = elem[0] + item_duration[0]
                else:
                    if listofelems[index][0][:9] == listofelems[max(index - 1, 0)][0][:9]:
                        listofelems[index][0] = listofelems[index][0] + item_duration[2]
        return listofelems

    def buy_item(self, id, activate_it=False):
        response = self.session.get(
            url=self.index_php + 'page=shop&ajax=1&type={}'.format(id),
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).text
        if activate_it:
            activateToken = re.search(r'var token\s?=\s?"([^"]*)";', str(response)).group(1)
            response2 = self.session.post(
                url=self.index_php + 'page=inventory',
                data={'ajax': 1,
                      'token': activateToken,
                      'referrerPage': "ingame",
                      'buyAndActivate': id},
                headers={'X-Requested-With': 'XMLHttpRequest'}
            ).json()
        else:
            buyToken = re.search(r'var token\s?=\s?"([^"]*)";', str(response)).group(1)
            response2 = self.session.post(
                url=self.index_php + 'page=buyitem&item={}'.format(id),
                data={'ajax': 1,
                      'token': buyToken},
                headers={'X-Requested-With': 'XMLHttpRequest'}
            ).json()
        list = []
        if not response2['error']:
            if activate_it:
                item_data = response2['message']['item']
            else:
                item_data = response2['item']

            class Item:
                name = item_data['name']
                costs = int(item_data['costs'])
                duration = int(item_data['duration'])
                effect = item_data['effect']
                amount = int(item_data['amount'])
                list = [
                    name, costs, duration, effect, amount
                ]

            return Item
        else:
            return False

    def activate_item(self, id):
        response = self.session.get(
            url=self.index_php + 'page=shop&ajax=1&type={}'.format(id),
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).text
        activateToken = re.search(r'var token\s?=\s?"([^"]*)";', str(response)).group(1)
        response2 = self.session.post(
            url=self.index_php + 'page=inventory&item={}&ajax=1'.format(id),
            data={'ajax': 1,
                  'token': activateToken,
                  'referrerPage': "shop"},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        list = []
        if not response2['error']:
            item_data = response2['message']['item']

            class Item:
                name = item_data['name']
                costs = int(item_data['costs'])
                duration = int(item_data['duration'])
                effect = item_data['effect']
                canbeused = bool(item_data['canBeActivated'])
                amount = int(item_data['amount'])
                list = [
                    name, costs, duration, effect, canbeused, amount
                ]

            return Item
        else:
            return False

    def fleet_coordinates(self, event, Coords):
        coordinate = [
            coords.find(class_=Coords).a.text
            for coords in event
        ]
        coordinate = [
            const.convert_to_coordinates(coords)
            for coords in coordinate
        ]
        destination = [
            dest.find('figure', {'class': 'planetIcon'})
            for dest in event
        ]
        destination = [
            const.convert_to_destinations(dest['class'])
            for dest in destination
        ]
        coordinates = []
        for coords, dest in zip(coordinate, destination):
            coords.append(dest)
            coordinates.append(coords)

        return coordinates

    def slot_fleet(self):
        response = self.session.get(
            self.index_php + 'page=ingame&component=fleetdispatch'
        ).text
        bs4 = BeautifulSoup4(response)
        slots = bs4.find('div', attrs={'id': 'slots', 'class': 'fleft'})
        slots = [
            slot.text
            for slot in slots.find_all(class_='fleft')
        ]
        fleet = re.search(':(.*)/(.*)', slots[0])
        fleet = [fleet.group(1), fleet.group(2)]
        expedition = re.search(' (.*)/(.*)\\n', slots[1])
        expedition = [
            expedition.group(1).replace(' ', ''),
            expedition.group(2)
        ]

        class Fleet:
            total = int(fleet[1])
            free = total - int(fleet[0])

        class Expedition:
            total = int(expedition[1])
            free = total - int(expedition[0])

        class Slot:
            fleet = Fleet
            expedition = Expedition

        return Slot

    def fleet(self):
        fleets = []
        fleets.extend(self.hostile_fleet())
        fleets.extend(self.friendly_fleet())
        return fleets

    def friendly_fleet(self):
        if not self.friendly():
            return []
        response = self.session.get(
            self.index_php + 'page=ingame&component=movement'
        ).text
        bs4 = BeautifulSoup4(response)
        fleetDetails = bs4.find_all(class_='fleetDetails')
        fleet_ids = bs4.find_all_partial(id='fleet')
        fleet_ids = [id['id'] for id in fleet_ids]
        fleet_ids = [
            int(re.search('fleet(.*)', id).group(1))
            for id in fleet_ids
        ]

        mission_types = [
            int(event['data-mission-type'])
            for event in fleetDetails
        ]
        return_flights = [
            bool(event['data-return-flight'])
            for event in fleetDetails
        ]
        arrival_times = [
            int(event['data-arrival-time'])
            for event in fleetDetails
        ]
        arrival_times = [
            datetime.fromtimestamp(timestamp)
            for timestamp in arrival_times
        ]

        destinations = self.fleet_coordinates(fleetDetails, 'destinationCoords')
        origins = self.fleet_coordinates(fleetDetails, 'originCoords')

        fleets = []
        for i in range(len(fleet_ids)):
            class Fleets:
                id = fleet_ids[i]
                mission = mission_types[i]
                diplomacy = const.diplomacy.friendly
                player_name = self.player
                player_id = self.player_id
                returns = return_flights[i]
                arrival = arrival_times[i]
                origin = origins[i]
                destination = destinations[i]
                list = [id, mission, diplomacy, player_name, player_id, returns,
                        arrival, origin, destination]

            fleets.append(Fleets)
        return fleets

    def hostile_fleet(self):
        if not self.attacked():
            return []
        response = self.session.get(
            url=self.index_php + 'page=componentOnly&component=eventList'
        ).text
        bs4 = BeautifulSoup4(response)

        eventFleet = bs4.find_all('span', class_='hostile')
        eventFleet = [child.parent.parent for child in eventFleet]

        fleet_ids = [id['id'] for id in eventFleet]
        fleet_ids = [
            re.search('eventRow-(.*)', id).group(1)
            for id in fleet_ids
        ]

        arrival_times = [
            int(event['data-arrival-time'])
            for event in eventFleet
        ]
        arrival_times = [
            datetime.fromtimestamp(timestamp)
            for timestamp in arrival_times
        ]

        destinations = self.fleet_coordinates(eventFleet, 'destCoords')
        origins = self.fleet_coordinates(eventFleet, 'coordsOrigin')

        player_ids = [
            int(id.find(class_='sendMail').a['data-playerid'])
            for id in eventFleet
        ]
        player_names = [
            name.find(class_='sendMail').a['title']
            for name in eventFleet
        ]

        fleets = []
        for i in range(len(fleet_ids)):
            class Fleets:
                id = fleet_ids[i]
                mission = 1
                diplomacy = const.diplomacy.hostile
                player_name = player_names[i]
                player_id = player_ids[i]
                returns = False
                arrival = arrival_times[i]
                origin = origins[i]
                destination = destinations[i]
                list = [
                    id, mission, diplomacy, player_name, player_id, returns,
                    arrival, origin, destination
                ]

            fleets.append(Fleets)
        return fleets

    def phalanx(self, coordinates, id):
        raise NotImplemented(
            'Phalanx get you banned if used with invalid parameters')

    def send_message(self, player_id, msg):
        response = self.session.get(self.index_php + 'page=chat').text
        chat_token = re.search('var ajaxChatToken = "(.*)"', response).group(1)
        response = self.session.post(
            url=self.index_php + 'page=ajaxChat',
            data={'playerId': player_id,
                  'text': msg,
                  'mode': 1,
                  'ajax': 1,
                  'token': chat_token},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        if 'OK' in response['status']:
            return True
        else:
            return False

    def rename_planet(self, id, new_name):
        self.session.get(
            url=self.index_php,
            params={'cp': id})
        response = self.session.get(
            url=self.index_php,
            params={'page': 'planetlayer'},
            headers={
                'Referer': f'{self.index_php}page=ingame'
                           f'&component=overview&cp={id}'
            }
        ).text
        token_rename = re.search("name='token' value='(.*)'", response).group(1)
        param = {'page': 'planetRename'}
        data = {
            'newPlanetName': new_name,
            'token': token_rename}
        response = self.session.post(
            url=self.index_php,
            params=param,
            data=data,
            headers={
                'Referer': f'{self.index_php}page=ingame'
                           f'&component=overview&cp={id}'
            }
        ).json()
        return response['status']

    def abandon_planet(self, id):
        self.session.get(
            url=self.index_php,
            params={'cp': id}
        )
        header = {
            'Referer': f'{self.index_php}page=ingame'
                       f'&component=overview&cp={id}'
        }
        response = self.session.get(
            self.index_php,
            params={'page': 'planetlayer'},
            headers=header
        ).text
        response = response[response.find('input type="hidden" name="abandon" value="'):]
        code_abandon = re.search(
            'name="abandon" value="(.*)"', response
        ).group(1)
        token_abandon = re.search(
            "name='token' value='(.*)'", response
        ).group(1)
        response = self.session.post(
            url=self.index_php,
            params={'page': 'checkPassword'},
            data={
                'abandon': code_abandon,
                'token': token_abandon,
                'password': self.password,
            },
            headers=header
        ).json()
        new_token = None
        if response.get("password_checked") and response["password_checked"]:
            new_token = response["newAjaxToken"]
        if new_token:
            self.session.post(
                url=self.index_php,
                params={
                    'page': 'planetGiveup'
                },
                data={
                    'abandon': code_abandon,
                    'token': new_token,
                    'password': self.password,
                },
                headers=header).json()
            self.session.get(url=self.index_php)
            return True
        else:
            return False

    def spyreports(self, firstpage=1, lastpage=30):
        report_links = []
        while firstpage <= lastpage:
            try:
                response = self.session.get(
                    url=self.index_php,
                    params={'page': 'messages',
                            'tab': 20,
                            'action': 107,
                            'messageId': -1,
                            'pagination': firstpage,
                            'ajax': 1}
                ).text
            except Exception as e:
                print(e)
                break
            bs4 = BeautifulSoup4(response)
            for link in bs4.find_all_partial(href='page=messages&messageId'):
                if link['href'] not in report_links:
                    report_links.append(link['href'])
            firstpage += 1
        reports = []
        for link in report_links:
            response = self.session.get(link).text
            bs4 = BeautifulSoup4(response)
            resources_list = bs4.find('ul', {'data-type': 'resources'})
            if resources_list is None:
                continue
            planet_coords = bs4.find('span', 'msg_title').find('a')
            if planet_coords is None:
                continue
            planet_coords = re.search(r'(.*?) (\[(.*?)])', planet_coords.text)
            report_datetime = bs4.find('span', 'msg_date').text
            api_code = bs4.find('span', 'icon_apikey')['title']
            resources_data = {}
            for resource in resources_list.find_all('li'):
                resource_name = resource.find('div')['class']
                resource_name.remove('resourceIcon')
                resources_data[resource_name[0]] = int(resource['title'].replace('.', ''))

            def get_tech_and_quantity(tech_type):
                tech_list = bs4.find('ul', {'data-type': tech_type})
                for tech in tech_list.find_all('li', {'class': 'detail_list_el'}):
                    tech_id = int(re.search(r'([0-9]+)', tech.find('img')['class'][0]).group(1))
                    tech_amount = int(tech.find('span', 'fright').text.replace('.', ''))
                    yield (tech_id, tech_amount)

            spied_data = {'ships': {}, 'defense': {}, 'buildings': {}, 'research': {}}
            const_data = {
                'ships': [const.ships.ship_name, 'shipyard'],
                'defense': [const.buildings.defense_name, 'defenses'],
                'buildings': [const.buildings.building_name, None],
                'research': [const.research.research_name, 'research']
            }
            for tech_type in spied_data.keys():
                for tech_id, tech_amount in get_tech_and_quantity(tech_type):
                    if tech_type == 'ships' and tech_id in [212, 217]:
                        tech_name = const.buildings.building_name(
                            (tech_id, None, None)
                        )
                    else:
                        tech_name = const_data[tech_type][0](
                            (tech_id, None, const_data[tech_type][1])
                        )
                    spied_data[tech_type].update({tech_name: tech_amount})

            class Report:
                name = planet_coords.group(1)
                position = const.convert_to_coordinates(planet_coords.group(2))
                moon = bs4.find('figure', 'moon') is not None
                datetime = report_datetime
                metal = resources_data['metal']
                crystal = resources_data['crystal']
                deuterium = resources_data['deuterium']
                resources = [metal, crystal, deuterium]
                fleet = spied_data['ships']
                defenses = spied_data['defense']
                buildings = spied_data['buildings']
                research = spied_data['research']
                api = re.search(r'value=\'(.+?)\'', api_code).group(1)
                list = [
                    name, position, moon, datetime, metal,
                    crystal, deuterium, resources, fleet,
                    defenses, buildings, research, api
                ]

            reports.append(Report)
        return reports

    def send_fleet(
            self,
            mission,
            id,
            where,
            ships,
            resources=(0, 0, 0), speed=10, holdingtime=0
    ):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=fleetdispatch&cp={}'
            .format(id)
        ).text
        send_fleet_token = re.search('var fleetSendingToken = "(.*)"', response)
        if send_fleet_token is None:
            send_fleet_token = re.search('var token = "(.*)"', response)
        form_data = {'token': send_fleet_token.group(1)}
        for ship in ships:
            ship_type = 'am{}'.format(ship[0])
            form_data.update({ship_type: ship[1]})
        form_data.update(
            {
                'galaxy': where[0],
                'system': where[1],
                'position': where[2],
                'type': where[3],
                'metal': resources[0],
                'crystal': resources[1],
                'deuterium': resources[2],
                'prioMetal': 1,
                'prioCrystal': 2,
                'prioDeuterium': 3,
                'mission': mission,
                'speed': speed,
                'retreatAfterDefenderRetreat': 0,
                'union': 0,
                'holdingtime': holdingtime
            }
        )
        response = self.session.post(
            url=self.index_php + 'page=ingame&component=fleetdispatch'
                                 '&action=sendFleet&ajax=1&asJson=1',
            data=form_data,
            headers={'X-Requested-With': 'XMLHttpRequest'}
        ).json()
        return response['success']

    def return_fleet(self, fleet_id):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=movement'
        ).text
        if "return={}".format(fleet_id) in response:
            token = re.search(
                'return={}'.format(fleet_id) + '&amp;token=(.*)" ', response
            ).group(1).split('"')[0]
            self.session.get(
                url=''.join([
                    self.index_php,
                    'page=ingame&component=movement&return={}&token={}'
                    .format(fleet_id, token)
                ])
            )
            return True
        else:
            return False

    def build(self, what, planet_id):
        type = what[0]
        amount = what[1]
        component = what[2]
        response = self.session.get(
            url=self.index_php +
                'page=ingame&component={}&cp={}'
                .format(component, planet_id)
        ).text

        build_token = re.search(r'var token\s?=\s?"([^"]*)";', response).group(1)

        params = {
            'technologyId': type,
            'amount': amount,
            'mode': 1,
            'token': build_token
        }

        self.session.post(
            url=self.index_php +
                'page=componentOnly&component=buildlistactions&action=scheduleEntry&asJson=1',
            data=params,
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )

    def deconstruct(self, what, id):
        type = what[0]
        component = what[2]
        cant_deconstruct = [34, 33, 36, 41, 212, 217]
        if component not in ['supplies', 'facilities'] or type in cant_deconstruct:
            return
        response = self.session.get(
            url=self.index_php +
                'page=ingame&component={}&cp={}'
                .format(component, id)
        ).text
        deconstruct_token = re.search(
            r"var downgradeEndpoint = (.*)token=(.*)\&",
            response
        ).group(2)
        self.session.get(
            url=self.index_php,
            params={'page': 'ingame',
                    'component': component,
                    'modus': 3,
                    'token': deconstruct_token,
                    'type': type}
        )

    def cancel_building(self, id):
        self.cancel('building', id)

    def cancel_research(self, id):
        self.cancel('research', id)

    def cancel(self, what_queue, id):
        response = self.session.get(
            url=self.index_php + 'page=ingame&component=overview',
            params={'cp': id}
        ).text
        cancel_token = re.search(
            rf"var cancelLink{what_queue} = (.*)token=(.*)\&",
            response
        ).group(2)
        parameters = re.search(
            rf"\"cancel{what_queue}\((.*)\, (.*)\,",
            response
        )
        if parameters is None:
            return
        self.session.get(
            url=self.index_php,
            params={'page': 'ingame',
                    'component': 'overview',
                    'modus': 2,
                    'token': cancel_token,
                    'action': 'cancel',
                    'type': parameters.group(1),
                    'listid': parameters.group(2)}
        )

    def collect_rubble_field(self, id):
        self.session.get(
            url=self.index_php +
                'page=ajax&component=repairlayer&component=repairlayer&ajax=1'
                '&action=startRepairs&asJson=1&cp={}'
                .format(id),
            headers={'X-Requested-With': 'XMLHttpRequest'})

    def is_logged_in(self):
        response = self.session.get(
            url='https://lobby.ogame.gameforge.com/api/users/me/accounts'
        ).json()
        if 'error' in response:
            return False
        else:
            return True

    def is_logged_in_uni(self):
        try:
            response = self.session.get(
                url=self.index_php
            ).text
            if 'Player' not in str(response):
                print("is_logged_in_uni: False")
                return False
            else:
                # print("is_logged_in_uni: True")
                return True
        except Exception as e:
            return False

    def relogin(self, universe=None):
        if universe is None:
            universe = self.universe
        OGame.__init__(self, universe, self.username, self.password,
                       self.user_agent, self.proxy)
        return OGame.is_logged_in(self)

    def keep_going(self, function):
        try:
            function()
        except:
            self.relogin()
            function()

    def logout(self):
        self.session.get(self.index_php + 'page=logout')
        self.session.put(
            'https://lobby.ogame.gameforge.com/api/users/me/logout'
        )
        return not OGame.is_logged_in(self)

    def buy_offer_of_the_day(self):
        response = self.session.get(
            url=self.index_php +
                'page=ingame&component=traderOverview').text

        time.sleep(random.randint(250, 1500) / 1000)

        response2 = self.session.post(
            url=self.index_php +
                'page=ajax&component=traderimportexport',
            data={
                'show': 'importexport',
                'ajax': 1
            },
            headers={'X-Requested-With': 'XMLHttpRequest'}).text

        time.sleep(random.randint(250, 1500) / 1000)

        bs4 = BeautifulSoup4(response2)

        try:
            item_available = bs4.find_partial(class_='bargain import_bargain take hidden').text
            return f'You have already accepted this offer!'
        except Exception as e:
            err = e
        try:
            item_price = bs4.find_partial(class_='price js_import_price').text
            item_price = int(item_price.replace('.', ''))
        except Exception as e:
            return f'err: {e}, failed to extract offer of the day price'

        try:
            planet_resources = re.search(r'var planetResources\s?=\s?({[^;]*});', response2).group(1)
            planet_resources = json.loads(planet_resources)
        except Exception as e:
            return f'err: {e}, failed to extract offer of the day planet resources'

        try:
            import_token = re.search(r'var importToken\s?=\s?"([^"]*)";', response2).group(1)
        except Exception as e:
            return f'err: {e}, failed to extract offer of the day import_token'

        try:
            multiplier = re.search(r'var multiplier\s?=\s?({[^;]*});', response2).group(1)
            multiplier = json.loads(multiplier)
        except Exception as e:
            return f'err: {e}, failed to extract offer of the day multiplier'

        form_data = {'action': 'trade'}

        remaining = item_price

        for celestial in list(planet_resources.keys()):
            metal_needed = int(planet_resources[celestial]['input']['metal'])
            if remaining < metal_needed * float(multiplier['metal']):
                metal_needed = math.ceil(remaining / float(multiplier['metal']))

            remaining -= metal_needed * float(multiplier['metal'])

            crystal_needed = int(planet_resources[celestial]['input']['crystal'])
            if remaining < crystal_needed * float(multiplier['crystal']):
                crystal_needed = math.ceil(remaining / float(multiplier['crystal']))

            remaining -= crystal_needed * float(multiplier['crystal'])

            deuterium_needed = int(planet_resources[celestial]['input']['deuterium'])
            if remaining < deuterium_needed * float(multiplier['deuterium']):
                deuterium_needed = math.ceil(remaining / float(multiplier['deuterium']))

            remaining -= deuterium_needed * float(multiplier['deuterium'])

            form_data.update(
                {
                    'bid[planets][{}][metal]'.format(str(celestial)): '{}'.format(int(metal_needed)),
                    'bid[planets][{}][crystal]'.format(str(celestial)): '{}'.format(str(crystal_needed)),
                    'bid[planets][{}][deuterium]'.format(str(celestial)): '{}'.format(str(deuterium_needed)),
                }
            )

        form_data.update(
            {
                'bid[honor]': '0',
                'token': '{}'.format(import_token),
                'ajax': '1'
            }
        )

        time.sleep(random.randint(1500, 3000) / 1000)

        response3 = self.session.post(
            url=self.index_php +
                'page=ajax&component=traderimportexport&ajax=1&action=trade&asJson=1',
            data=form_data,
            headers={'X-Requested-With': 'XMLHttpRequest'}).json()

        try:
            new_token = response3['newAjaxToken']
        except Exception as e:
            return f'err: {e}, failed to extract offer of the day newAjaxToken'

        form_data2 = {
            'action': 'takeItem',
            'token': '{}'.format(new_token),
            'ajax': '1'
        }

        time.sleep(random.randint(250, 1500) / 1000)

        response4 = self.session.post(
            url=self.index_php +
                'page=ajax&component=traderimportexport&ajax=1&action=takeItem&asJson=1',
            data=form_data2,
            headers={'X-Requested-With': 'XMLHttpRequest'}).json()

        getitem = False
        if not response4['error']:
            getitem = True
        return getitem

    def yeast(self, num):
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        length = len(alphabet)
        encoded = ""
        while num > 0:
            encoded = str(alphabet[int(num % length)]) + encoded
            num = int(math.floor(float(num / length)))
        return encoded

    def websocket_init(self):
        response = self.session.get(
            url=self.index_php +
                'page=ingame&component=traderOverview').text

        try:
            chathost = re.search(r'var nodeUrl\s?=\s?"https:\\/\\/([^:]+):(\d+)\\/socket.io\\/socket.io.js"',
                                 response).group(1)

            chatport = re.search(r'var nodeUrl\s?=\s?"https:\\/\\/([^:]+):(\d+)\\/socket.io\\/socket.io.js"',
                                 response).group(2)

        except Exception as e:
            return f'err: {e}, failed to extract Chat Host and Port'

        dt = datetime.now(timezone.utc)
        utc_timestamp = dt.timestamp()
        token = self.yeast(utc_timestamp * 1000)

        url_combined = f'https://{chathost}:{chatport}/socket.io/?EIO=4&transport=polling&t={token}' \
            .format(chathost=chathost, chatport=chatport, token=token)

        response2 = self.session.get(
            url=url_combined,
            data='40/chat,',
        ).text

        sid = re.search(r'"sid":"([^"]+)"', response2).group(1)

        return chathost, chatport, token, sid


def solve_captcha(question_raw, icons_raw):
    hash_values = {
        "cc6c3193cec65c39": "star",
        "ccc6713993e664cc": "bulb",
        "9ad9657131c6d632": "flower",
        "c36938966c93d36c": "magnet",
        "9339398e6ce4e68c": "castle",
        "cccc333336cccc33": "fork",
        "cf65389bc78e3830": "apple",
        "8b982c63a69ecb69": "sun",
        "cbd9313232c6ce99": "cherry",
        "964f69b49443db58": "bicycle",
        "98d3673c646c9ac6": "pencils",
        "cf4d30c2cd92b339": "keys",
        "926d6493d96c3699": "scissors",
        "d8c9a736c89c2e63": "pirate flag",
        "cfcb3034c3938ecc": "orange",
        "cc2833c7ce999966": "raindrop",
        "9b3964c6ce3991b1": "cloud",
        "cec630393363cec6": "ballon",
        "c4313bcec531ce66": "crown",
        "c93332cc6733339c": "candle",
        "c5391ac76f64903b": "laptop",
        "c6ce3931c661c6ce": "book",
        "9293696ec7859c63": "fried egg",
        "e4999b66646d6499": "top hat",
        "91b66a4995b668d9": "glasses",
        "cbc66c3892e3cccc": "dice",
        "cc9c3363cc9c7163": "planet",
        "cc6c33936c6c9a39": "bell",
        "9696314d4c79b396": "carrot",
        "909a6f65909ac7e3": "gamepad",
        "c766388c6399ce66": "moon",
        "8c8e7331c5cf26cc": "globe",
        "cbc63c383322cdcd": "doughnut",
        "8e93696c33939696": "tree",
        "c3cb3c34c3cb9c2c": "rainbow",
        "cc3333cc66669966": "bottle",
        "cccc333132c7d31b": "ice cream",
        "999b6664339b88ce": "paintbrush",
        "869b3964339bce2c": "hamburger",
        "cfc7303882c7cd3a": "heart",
        "92366dc93266cd39": "banana",
        "c43d37c3584e7073": "guitar",
        "9a666599c3649e66": "mug",
        "c36d3c92c3cd3c92": "sailling",
    }

    # paths
    path_of_the_directory_captchas = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'captcha', 'captchas')
    path_of_the_directory_questions = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'captcha', 'questions')

    try:
        os.makedirs(path_of_the_directory_captchas)
    except FileExistsError:
        pass
    try:
        os.makedirs(path_of_the_directory_questions)
    except FileExistsError:
        pass

    final_answer = -1
    answer_list = []
    answer_dict = {}

    in_memory_file = io.BytesIO(icons_raw)
    img = Image.open(in_memory_file)

    # size of images
    left = 0
    top = 0
    right = 60
    bottom = 60

    # cut icons into pieces and create hash
    i = 0
    while i < 4:
        img_res = img.crop((left, top, right, bottom))
        newsize = (100, 100)
        img_res = img_res.resize(newsize)
        img_res = img_res.save(os.path.join(path_of_the_directory_captchas, "captcha_" + str(i) + ".png"))

        # create hash
        hash_img = imagehash.phash(
            Image.open(os.path.join(path_of_the_directory_captchas, "captcha_" + str(i) + ".png")))

        # save file with hash as name
        shutil.copy(os.path.join(path_of_the_directory_captchas, "captcha_" + str(i) + ".png"),
                    os.path.join(path_of_the_directory_captchas, str(hash_img) + ".png"))

        try:
            answer_list.append(hash_values[str(hash_img)])
            answer_dict.update({hash_values[str(hash_img)]: i})
        except KeyError:
            print(f'DEBUG found no word for hash {hash_img}')

        right = right + 60
        left = left + 60
        i = i + 1

    # get question with OCR
    with open(os.path.join(path_of_the_directory_questions, "question.png"), "wb") as file:
        file.write(question_raw)

    img = cv2.imread(os.path.join(path_of_the_directory_questions, "question.png"))
    scale_percent = 160  # percent of original size
    width = int(img.shape[1] * scale_percent / 100)
    height = int(img.shape[0] * scale_percent / 100)
    dim = (width, height)
    # resize image
    resized = cv2.resize(img, dim, interpolation=cv2.INTER_AREA)
    gry = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gry, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    txt = image_to_string(thresh)
    word_captcha = txt.lower().strip().strip(',.').replace('\n', ' ').replace('\r', '')
    try:
        shutil.copy(os.path.join(path_of_the_directory_questions, "question.png"),
                    os.path.join(path_of_the_directory_questions, str(word_captcha) + ".png"))
    except Exception as e:
        print(f'error copy question {e}')

    # get final answer
    for answer in answer_list:
        if answer in word_captcha:
            final_answer = answer_dict[answer]

    if final_answer >= 0:
        print(f'answer found: {final_answer}')
        return final_answer
    else:
        final_answer = 0
        print(f'no answer found, use: {final_answer}')
        return final_answer


# Blackbox
def encode_uri_component(s):
    return quote(s, safe="!~*'()")


def pseudo_b64(s):
    lut = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
    len_mod3 = len(s) % 3
    out = ""
    for i in range(0, len(s), 3):
        c1 = ord(s[i])
        c2 = ord(s[i + 1]) if i + 1 < len(s) else 0
        c3 = ord(s[i + 2]) if i + 2 < len(s) else 0
        t = c1 << 16 | c2 << 8 | c3
        out += lut[t >> 18 & 63] + lut[t >> 12 & 63] + lut[t >> 6 & 63] + lut[t & 63]
    return out[:len_mod3 - 3] if len_mod3 > 0 else out


def encrypt(s):
    s = encode_uri_component(s)
    out = s[0]
    for i in range(1, len(s)):
        out += chr((ord(out[i - 1]) + ord(s[i])) % 256)
    return pseudo_b64(out)


def js_iso_time(d):
    return d.isoformat()[:23] + "Z"


def get_vector(d):
    def rand_char() -> str:
        return chr(int(32 + random.random() * 94))

    def gen_new_xvec() -> str:
        part1 = "".join(rand_char() for _ in range(100))
        ts = str(int(d.timestamp() * 1000))
        return f"{part1} {ts}"

    x_vec = gen_new_xvec()
    x_vec_b64 = base64.standard_b64encode(x_vec.encode()).decode()

    return x_vec_b64


def get_blackbox():
    obj = {
        "v": 9,  # Version
        "tz": "Europe/Berlin",  # Timezone
        "dnt": False,  # do not track
        "product": "Blink",
        "osType": "Windows",
        "app": "Blink",
        "vendor": "Google Inc.",
        "mem": 8,
        "con": 4,
        "lang": "de-DE,de,en-US,en",
        "plugins": "f473d473013d58cee78732e974dd4af2e8d0105449c384658cbf1505e40ede50",
        "gpu": "Google Inc. (Intel),ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fonts": "67574c80452bcc244b31e19a66a5f4768b48be6d88dfc462d5fa7d8570ed87da",
        "audioC": "c6a7feda4a58521c20f9ffd946a0ce3edfac57a54e35e73857e710c85a9e4415",
        "width": 1900,
        "height": 1080,
        "depth": 24,
        # "lStore": True,
        # "sStore": True,
        "video": "1f03b77fda33742261bea0d27e6423bf22d2bf57febc53ae75b962f6e523cc02",
        "audio": "c76e22cc6aa9f5a659891983b77cd085a3634dd6f6938827ab5a4c6c61a628e5",
        "media": "d15bbda6b8af6297ea17f2fb6a724d3bacde9b2e1285a951ee148e4cd5cc452c",
        "permissions": "86beeaf2f319e30b7dfedc65ccb902a989a210ffb3d4648c80bd0921aa0a2932",
        "audioFP": 35.738334245979786,
        "webglFP": "7d6f8162c7c6be70d191585fd163f34dbc404a8b4f6fcad4d2e660c7b4e4b694",
        "canvasFP": 732998116,
        "creation": js_iso_time(datetime.utcnow()),
        "uuid": "ajs3innzou3hulixyriljvj89by",
        "d": randint(300, 500),  # how long it took to collect data
        "osVersion": "10",
        "vector": get_vector(datetime.now()),
        "userAgent": user_agent_raw,
        "serverTimeInMS": js_iso_time(datetime.utcnow().replace(microsecond=1)),
        "request": None
    }

    en_obj = []
    for k, v in obj.items():
        en_obj.append(v)

    en_obj = json.dumps(en_obj, separators=(",", ":"))
    return encrypt(en_obj)


def BeautifulSoup4(response):
    parsed = BeautifulSoup(response, features="html5lib")

    def find_partial(**kwargs):
        for key, value in kwargs.items():
            kwargs[key] = re.compile(value)
        return parsed.find(**kwargs)

    def find_all_partial(**kwargs):
        for key, value in kwargs.items():
            kwargs[key] = re.compile(value)
        return parsed.find_all(**kwargs)

    parsed.find_partial = find_partial
    parsed.find_all_partial = find_all_partial
    return parsed
