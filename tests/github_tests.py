import unittest
import urlparse

import mock

from bootstrap_salt.deploy_lib import github


class GithubTest(unittest.TestCase):

    def setUp(self):
        token_mock = mock.MagicMock(return_value='sometoken')
        content_mock = mock.Mock(side_effect=self.content_side_effect)
        github.get_github_token = token_mock
        github.get_paginated_content = content_mock

        self.orgs_document = [
            {'slug': 'teamA', 'id': '123456'},
            {'slug': 'teamB', 'id': '789012'},
        ]

        rsa_pub_key = '''ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEA5KtkJ1gcLKYa''' \
                      '''EKzCzEd7A4iP7LKs8Fx87TT0fElrIYP7CoSGaK4DaOkkYhyOX''' \
                      '''gV2Togj1kRUpgazwiybi/5xW0T8RUZa9kSPp9zJADTiTR8TOU''' \
                      '''Wu1pl/nRMKUdmooY6LHtfOML633FX/Aj5OeiA7RfiEZv5odNRt''' \
                      '''Tlz8m9eZsMs= sample_rsa_key'''

        dsa_pub_key = '''ssh-dss AAAAB3NzaC1kc3MAAACBAPq/cb/flXMYNzrnCyF9Q''' \
                      '''IlVYWZa+uCGQ2pBvwIRMrsFk+lrVgWqV6eVL6DVgjz8n1rphf''' \
                      '''qYCg12SNhkKLY3vbf6656iO7V+bFt6zmWdp6CmVyATMPEImsd''' \
                      '''b1q+p32xRCUC+zVA5hSyMdW7RUVBQiIDUScNb13AVpom72A''' \
                      '''eP0IHJAAAAFQDOBHsfqF37SdIcQClH9HJQSYY9vQAAAIEA''' \
                      '''souZoZRi2ruS0E7P+oM6zKjIJR2If4m1SWDcEyh2RHaGBX''' \
                      '''l9sCPpBnIgrCmXKD4OBd52UnyIau4FYGj3FuNoo8AMUhcna8''' \
                      '''xvc4pH9RJd70syC6yub1r00qVsaiqULYIe+lh06TqPLEt+yn''' \
                      '''TVDMm7Mk9Gd4M7IKy3DqKdffZtGCUAAACBAJ16Kvvr6YDm644x''' \
                      '''UqUax5cktrKyW730Do0xmAGStxP5TMHCDgMNlkcdcTpReJxaOS''' \
                      '''hgnpvysdUrkMjbI/UPTkcJRtonVE4K7tTs4y0/zpCxa812haG8''' \
                      '''dTOABK9rioyos57v3qkemrqBy9f7DNUk3cRXkmiPphIxoO87Hm''' \
                      '''NDBCjI sample_dsa_key'''
        invalid_pub_key = 'ssh-notvalid blah invalid_key'
        not_a_key = 'notakey'
        self.public_keys = {
            'rsa': {
                'key': rsa_pub_key,
                'fingerprint': '09:05:ee:46:39:5d:87:e2:05:42:07:0b:c7:4a:63:a9'
            },
            'dsa': {
                'key': dsa_pub_key,
                'fingerprint': '35:53:6f:27:fe:39:8b:d8:dd:87:19:f3:40:d2:84:6a'
            },
            'invalid': {
                'key': invalid_pub_key,
                'fingerprint': 'blah'
            },
            'not_a_key': {
                'key': not_a_key,
                'fingerprint': 'blah'
            }
        }

        self.users_document = [self.public_keys['rsa'], self.public_keys['dsa']]

    def handle_orgs_request(self, path):
        return self.orgs_document

    def handle_users_request(self, path):
        if path.split('/')[-1] == 'keys':
            user = path.split('/')[2]
            if user == 'good_user':
                return [self.public_keys['rsa']]
            elif user == 'bad_user':
                raise github.GithubRequestException
            elif user == 'good_invalid_keys':
                return [self.public_keys['invalid']]
            elif user == 'good_no_keys':
                return []
            elif user == 'good_all_keys':
                return [self.public_keys['rsa'], self.public_keys['dsa']]

    def content_side_effect(self, *args, **kwargs):
        # immitate github's api responses
        if not args:
            raise Exception
        url = args[0]
        path = urlparse.urlparse(url).path
        responses_map = {
            'orgs': self.handle_orgs_request,
            'users': self.handle_users_request
        }
        if path == '/':
            return {}
        return responses_map.get(path.split('/')[1])(path)

    def test_get_org_team(self):
        # test existing team
        x = github.get_org_team('teamA')
        self.assertEquals(x['slug'], 'teamA')

        # test non existing team
        self.assertRaises(github.InvalidTeamException,
                          github.get_org_team, 'nonexistingteam')

    def test_get_key_fingerprint(self):

        # test rsa fingerprint
        rsa_fingerprint = github.get_key_fingerprint(self.public_keys['rsa'])
        self.assertEquals(rsa_fingerprint,
                          self.public_keys['rsa']['fingerprint'])

        # test dsa fingeprint
        dsa_fingerprint = github.get_key_fingerprint(self.public_keys['dsa'])
        self.assertEquals(dsa_fingerprint,
                          self.public_keys['dsa']['fingerprint'])

        # test invalid key format
        self.assertRaises(github.InvalidKey,
                          github.get_key_fingerprint,
                          self.public_keys['invalid'])

        # test invalid string
        self.assertRaises(github.InvalidKey,
                          github.get_key_fingerprint,
                          self.public_keys['not_a_key'])

    def test_get_user_keys(self):

        # existing user with key
        self.assertEquals(github.get_user_keys('good_user'),
                          [self.public_keys['rsa']])

        # non existing user
        self.assertRaises(github.GithubRequestException, github.get_user_keys,
                          'bad_user')

        # existing user with no keys
        self.assertEquals([], github.get_user_keys('good_no_keys'))

        # existing user with multiple keys filtered by fingerprint
        self.assertEquals(
            [self.public_keys['rsa']],
            github.get_user_keys(
                'good_all_keys',
                fingerprints=[self.public_keys['rsa']['fingerprint']]))

        # existing user with single key and multiple fingerprints
        # in the fingerprint list
        self.assertEquals(
            [self.public_keys['rsa']],
            github.get_user_keys(
                'good_user',
                fingerprints=[self.public_keys['rsa']['fingerprint'],
                              self.public_keys['rsa']['fingerprint']]))
