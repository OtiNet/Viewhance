from __future__ import unicode_literals
import sys
import os
import json
import subprocess
from io import open
from time import time
from shutil import rmtree, copy
from collections import OrderedDict

try:
    from urllib import urlretrieve as download
except:
    from urllib.request import urlretrieve as download


os.chdir(os.path.split(os.path.abspath(__file__))[0])
pj = os.path.join

def norm_cygdrive(path):
    return '/cygdrive/' + path[0] + path[2:].replace('\\', '/') if path[1] == ':' else path

class Platform(object):
    ext = os.path.basename(os.path.dirname(__file__))
    update_file = 'Update.plist'
    requires_all_strings = True
    l10n_dir = 'locales'

    def __init__(self, build_dir, config, languages, desc_string, package_name):
        self.build_dir = os.path.join(
            build_dir,
            config['name'] + '.safariextension'
        )
        self.config = config
        self.languages = languages
        self.desc_string = desc_string
        self.package_name = package_name

    def __del__(self):
        for param in ['description', 'build_number', 'update_file']:
            if param in self.config:
                del self.config[param]

    def write_manifest(self):
        info_plist_path = os.path.join(self.build_dir, 'Info.plist')

        with open(info_plist_path, 'wt', encoding='utf-8', newline='\n') as f:
            def_lang = self.languages[self.config['def_lang']]
            self.config['description'] = def_lang[self.desc_string]
            self.config['build_number'] = int(time())
            self.config['update_file'] = self.update_file

            with open(os.path.join('meta', 'Info.plist'), 'r') as info_plist:
                f.write(info_plist.read().format(**self.config))

    def write_update_file(self):
        if not self.config['update_url']:
            return

        update_file = os.path.join(self.build_dir, '..', self.update_file)

        with open(update_file, 'wt', encoding='utf-8', newline='\n') as f:
            with open(os.path.join('meta', self.update_file), 'r') as tmpl:
                f.write(tmpl.read().format(**self.config))

    def write_locales(self, lng_strings):
        locale_files = {
            'options': 'strings.js'
        }

        for alpha2 in lng_strings:
            locale_dir = os.path.join(self.build_dir, self.l10n_dir, alpha2)

            try:
                os.makedirs(locale_dir)
            except:
                pass

            if not os.path.exists(locale_dir):
                sys.stderr.write(
                    'Falied to create locale directory:\n' + locale_dir + '\n'
                )
                continue

            lang = lng_strings[alpha2]

            for grp in locale_files:
                if grp not in lang:
                    continue

                locale = open(
                    os.path.join(locale_dir, locale_files[grp]),
                    'wt', encoding='utf-8', newline='\n'
                )

                with locale as f:
                    f.write('vAPI.l10nData = ')
                    f.write(
                        json.dumps(
                            lang[grp],
                            separators=(',', ':'),
                            ensure_ascii=False
                        )
                    )
                    f.write(';\n')

    def write_files(self, use_symlinks=False):
        copy(pj('meta', 'Settings.plist'), pj(self.build_dir))

    def write_package(self):
        key = pj('secret', 'key.pem')
        certs = pj('secret', 'certs')
        tmp_dir = pj(os.path.dirname(self.build_dir), '.tmp')
        package = self.package_name + '.' + self.ext

        if not os.path.isfile(key):
            sys.stderr.write(key + ' is missing\n')
            return

        if not os.path.isfile(pj(certs, 'safari_extension.cer')):
            sys.stderr.write(
                pj(certs, 'safari_extension.cer') + ' is missing\n'
            )
            return

        try: os.remove(package)
        except: pass

        try: rmtree(tmp_dir)
        except: pass

        try: os.makedirs(tmp_dir)
        except: pass

        try: os.makedirs(certs)
        except: pass

        if not os.path.isfile(pj(certs, 'AppleWWDRCA.cer')):
            print('Downloading AppleWWDRCA.cer...')
            download(
                'https://developer.apple.com/certificationauthority/AppleWWDRCA.cer',
                pj(certs, 'AppleWWDRCA.cer')
            )

        if not os.path.isfile(pj(certs, 'AppleIncRootCertificate.cer')):
            print('Downloading AppleIncRootCertificate.cer...')
            download(
                'https://www.apple.com/appleca/AppleIncRootCertificate.cer',
                pj(certs, 'AppleIncRootCertificate.cer')
            )

        subprocess.call([
            'xar', '-czf', package,
            '--compression-args=9',
            '--distribution',
            '--directory', os.path.dirname(self.build_dir),
            os.path.basename(self.build_dir)
        ])

        sig_len = len(subprocess.Popen(
            ['openssl', 'dgst', '-binary', '-sign', key, key],
            stdout=subprocess.PIPE
        ).stdout.read())

        digest_dat = pj(tmp_dir, self.ext + '_digest.dat')
        sig_dat = pj(tmp_dir, self.ext + '_sig.dat')

        subprocess.call([
            'xar', '--sign', '-f', package,
            '--digestinfo-to-sign', digest_dat,
            '--sig-size', str(sig_len),
            '--cert-loc', pj(certs, 'safari_extension.cer'),
            '--cert-loc', pj(certs, 'AppleWWDRCA.cer'),
            '--cert-loc', pj(certs, 'AppleIncRootCertificate.cer')
        ])

        subprocess.call([
            'openssl', 'rsautl', '-sign', '-inkey', key,
            '-in', digest_dat, '-out', sig_dat
        ])

        subprocess.call(['xar', '--inject-sig', sig_dat, '-f', package])

        try: rmtree(tmp_dir)
        except: pass
