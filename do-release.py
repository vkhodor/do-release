#!/usr/bin/env python3

from zipfile import ZipFile
from shutil import copyfile
import os
import sys
import time
from artifactory import ArtifactoryPath
import semantic_version

from config import SERVICE_STOP, SERVICE_START
from config import TMP_APP_FILE, BUILD_INFO_FILE, ARTIFACTORY_TMPL_URL, DEFAULT_APP_FILE


class AppInterface(object):
    def get_version(self):
        pass

    def get_semantic_version(self):
        str_ver = normalize_version(str(self.get_version()).split('-')[-1])
        return semantic_version.Version(str_ver)

    def __gt__(self, other):
        if self.get_semantic_version() > other.get_semantic_version():
            return True
        return False

    def __eq__(self, other):
        if other is None:
            return False
        if self.get_semantic_version() == other.get_semantic_version():
            return True
        return False

    def __ne__(self, other):
        if other is None:
            return True
        return self.get_semantic_version() != other.get_semantic_version()


class CurrentApp(AppInterface):
    def __init__(self, path):
        self.__path=path

    def get_version(self):
        try:
            zip_file = ZipFile(self.__path, 'r')
            for f in zip_file.namelist():
                if f.endswith(BUILD_INFO_FILE):
                    zip_file.extract(f, '/tmp/_app'.format(BUILD_INFO_FILE))

                    with open('/tmp/_app/META-INF/{0}'.format(BUILD_INFO_FILE)) as fo:
                        for line in [f for f in fo.readlines() if 'build.version' in f]:
                            if len(line) > 0:
                                return clean_version(line.split('=')[1].strip())
        except Exception as e:
            return '0.0.0'
        return '0.0.0'


def check_version(str_version):
    for d in str_version.split('.'):
        if d.isdigit() is not True:
            return False
    return True


def normalize_version(str_version):
    if check_version(str_version) is not True:
        return '0.0.0'

    count_of_digits = len(str_version.split('.'))
    prefix = '.0' * (3 - count_of_digits)

    return '{0}{1}'.format(str_version, prefix)


def clean_version(string):
    return string.lower().replace('release-','').replace('-snapshot', '').replace('master.', '')


class LatestArtifactApp(AppInterface):
    def __init__(self, project_name, artifact_type, app_name):
        self.__url = ARTIFACTORY_TMPL_URL.format(artifact_type, project_name, app_name)
        self.__set_path()
        self.__version = clean_version(str(self.__path).split('/')[-1].strip())
        self.__download_path = ArtifactoryPath('{0}/{1}-{2}.jar'.format(str(self.__path), app_name, self.__version))

    def __set_path(self):
        dict_paths = {}
        for url in ArtifactoryPath(self.__url):
            cleaned_version = clean_version(str(url).split('/')[-1])
            str_ver = normalize_version(cleaned_version)
            sv = semantic_version.Version(str_ver)
            dict_paths[sv] = url
        self.__path = dict_paths[sorted(dict_paths.keys())[-1]]

    def get_version(self):
        return self.__version

    def get_path(self):
        return self.__path

    def get_download_path(self):
        for url in ArtifactoryPath(self.__url):
            if self.__version in str(url):
                for u in url:
                    if '.jar' in str(u):
                        return u
        return self.__download_path

    def download(self, path_to_download):
        download_path = self.get_download_path()
        try:
            with download_path.open() as fd:
                with open(path_to_download, 'wb') as out:
                    out.write(fd.read())
        except MemoryError:
            return False
        return True


def service_stop(app_name):
    cmd = SERVICE_STOP.format(app_name)
    return os.system(cmd)


def service_start(app_name):
    cmd = SERVICE_START.format(app_name)
    return os.system(cmd)


def do_release(from_file, to_file, app_name):
    copyfile(from_file, to_file)
    service_stop = SERVICE_STOP.format(app_name)
    service_start = SERVICE_START.format(app_name)
    result = os.system('{0}; {1}'.format(service_stop, service_start))
    return result


def usage_exit(args, code):
    print('Usage: {0} <project_name> <release|snapshot> <app_name> [force]'.format(args[0]))
    print('Example: {0} rtb snapshot data-sync'.format(args[0]))
    print('Example: {0} rtb release bundle-distance force'.format(args[0]))
    exit(code)


def main(args):

    if len(args) < 4:
        usage_exit(args, 1)

    project_name = args[1]
    release_type = args[2]
    force = False
    try:
        if args[4] != 'force':
            usage_exit(args, 1)
        force = True
    except IndexError:
        pass

    if release_type not in ['release', 'snapshot']:
        usage_exit(args, 1)

    app_name = args[3]
    print('[INF] project: {0}, type: {1}, app: {2}'.format(project_name, release_type, app_name))

    latest_artifact = LatestArtifactApp(project_name, release_type, app_name=app_name)
    current_app = CurrentApp(DEFAULT_APP_FILE.format(app_name))

    print('[INF] artifact: {0}, installed: {1}'.format(latest_artifact.get_version(), current_app.get_version()))

    if latest_artifact != current_app or force:
        print('[INF] Forcing release: {0}'.format(str(force)))
        print('[INF] LatestArtifact: {0} != Installed App: {1}'.format(latest_artifact.get_version(), current_app.get_version()))
        print('[INF] Downloading latest {0}.jar...'.format(app_name))
        if not latest_artifact.download(TMP_APP_FILE.format(app_name)):
            service_stop(app_name)
            if not latest_artifact.download(TMP_APP_FILE.format(app_name)):
                raise Exception('latest_artifact.download', 'returned False')

        print('[INF] Doing release...')
        result = do_release(TMP_APP_FILE.format(app_name), DEFAULT_APP_FILE.format(app_name), app_name)
        exit(result)

    print('[INF] Do nothing.')
    exit(0)


if __name__ == '__main__':
    try:
        main(sys.argv)
    except Exception as e:
        print('[ERR] exception: {0}'.format(e))
        print('[INF] Sleep for 5 min and try again.')
        time.sleep(300) # sleep for 5 minutes
        main(sys.argv)


class MockApp(AppInterface):
    def __init__(self, version='release-1.180.3'):
        self.__version = version

    def get_version(self):
        return self.__version


def test_clean_version():
    assert clean_version('release-1.1.1') == '1.1.1'
    assert clean_version('master.100-SNAPSHOT') == '100'


def test_gt_app():
    great_app = MockApp(version='release-1.180.7')
    small_app = MockApp(version='release-1.180.3')
    assert great_app > small_app


def test_ne_app():
    some_app = MockApp(version='release-1.180.7')
    other_app = MockApp(version='release-1.180.2')
    assert some_app != other_app


def test_eq_app():
    great_app = MockApp(version='release-1.180.7')
    small_app = MockApp(version='release-1.180.3')
    assert great_app != small_app
    eq_app = MockApp(version='release-1.180.7')
    assert great_app == eq_app


def test_check_version():
    assert check_version('z.1.1') == False
    assert check_version('1.2.3') == True
    assert check_version('1') == True
    assert check_version('1.2.3.4.5.6') == True


def test_mormalize_version():
    assert normalize_version('1.2') == '1.2.0'
    assert normalize_version('1.2.3') == '1.2.3'
    assert normalize_version('sdfsdf') == '0.0.0'
