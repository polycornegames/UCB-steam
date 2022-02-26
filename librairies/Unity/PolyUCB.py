import copy
import operator
from typing import Dict, List, re, Optional

import requests

from librairies import LOGGER
from librairies.Unity.classes import Build, UCBBuildStatus
from librairies.logger import LogLevel


# region UNITY_LIBRARY
class PolyUCB:
    def __init__(self, unity_org_id: str, unity_project_id: str, unity_api_key: str):
        self._unity_org_id: str = unity_org_id
        self._unity_project_id: str = unity_project_id
        self._unity_api_key: str = unity_api_key

        self.__builds: Optional[List[Build]] = None

        self.builds_categorized: Dict[str, List[Build]] = dict()
        self.builds_categorized['success']: List[Build] = list()
        self.builds_categorized['building']: List[Build] = list()
        self.builds_categorized['failure']: List[Build] = list()
        self.builds_categorized['canceled']: List[Build] = list()
        self.builds_categorized['unknown']: List[Build] = list()

    @property
    def unity_org_id(self):
        return self._unity_org_id

    @property
    def unity_project_id(self):
        return self._unity_project_id

    @property
    def unity_api_key(self):
        return self._unity_api_key

    def update(self):
        """
        Update the buildtargets information with UnityCloudBuild current builds status
        """
        self.__builds = self.__get_all_builds__()

        self.builds_categorized['success'].clear()
        self.builds_categorized['building'].clear()
        self.builds_categorized['failure'].clear()
        self.builds_categorized['canceled'].clear()
        self.builds_categorized['unknown'].clear()

        for build in self.__builds:
            if build.status == UCBBuildStatus.SUCCESS:
                self.builds_categorized['success'].append(build)
            elif build.status == UCBBuildStatus.QUEUED or build.status == UCBBuildStatus.SENTTOBUILDER or build.status == UCBBuildStatus.STARTED or build.status == UCBBuildStatus.RESTARTED:
                self.builds_categorized['building'].append(build)
            elif build.status == UCBBuildStatus.FAILURE:
                self.builds_categorized['failure'].append(build)
            elif build.status == UCBBuildStatus.CANCELED:
                self.builds_categorized['canceled'].append(build)
            else:
                self.builds_categorized['unknown'].append(build)

    def get_builds(self, platform: str = "") -> List[Build]:
        if self.__builds is None:
            self.update()

        data_temp: List[Build] = list()
        # filter on platform if necessary
        for build in self.__builds:
            if platform == "" or build.platform == platform:
                data_temp.append(build)

        data_temp.sort(key=lambda x: x.build_target_id)
        data_temp.sort(key=lambda x: x.number, reverse=True)

        return data_temp

    def __api_url(self) -> str:
        return 'https://build-api.cloud.unity3d.com/api/v1/orgs/{}/projects/{}'.format(self._unity_org_id,
                                                                                       self._unity_project_id)

    def __headers(self) -> dict:
        return {'Authorization': 'Basic {}'.format(self._unity_api_key)}

    def create_new_build_target(self, data, branch, user):
        name_limit = 64 - 17 - len(user)
        name = re.sub("[^0-9a-zA-Z]+", "-", branch)[0:name_limit]

        data['name'] = 'Autobuild of {} by {}'.format(name, user)
        data['settings']['scm']['branch'] = branch

        url = '{}/buildtargets'.format(self.__api_url())
        response = requests.post(url, headers=self.__headers(), json=data)

        if not response.ok:
            LOGGER.log("Creating build target " + data['name'] + " failed: " + response.text,
                       log_type=LogLevel.LOG_ERROR)

        info = response.json()
        return info['buildtargetid'], data['name']

    def delete_build_target(self, build_target_id: str):
        url = '{}/buildtargets/{}'.format(self.__api_url(), build_target_id)
        requests.delete(url, headers=self.__headers())

    def start_build(self, build_target_id: str):
        url = '{}/buildtargets/{}/builds'.format(self.__api_url(), build_target_id)
        data = {'clean': True}
        requests.post(url, headers=self.__headers(), json=data)

    def create_build_url(self, build_target_id: str, build_number: int) -> str:
        return 'https://developer.cloud.unity3d.com/build/orgs/{}/projects/{}/buildtargets/{}/builds/{}/log/compact/'.format(
            self._unity_org_id, self._unity_org_id, build_target_id, str(build_number)
        )

    def get_last_builds(self, build_target: str = "", platform: str = "") -> List[Build]:
        url = '{}/buildtargets?include_last_success=true'.format(self.__api_url())
        response = requests.get(url, headers=self.__headers())

        data_temp = []

        if not response.ok:
            LOGGER.log(f"Getting build template failed: {response.text}", log_type=LogLevel.LOG_ERROR)
            return data_temp

        data = response.json()
        data_temp = copy.deepcopy(data)
        # let's filter the result on the requested branch only
        for i in reversed(range(0, len(data))):
            build = data[i]

            # identify if the build is successful
            if "builds" not in build:
                # log(f"Missing builds field for {build["buildtargetid"]}", type=LOG_ERROR)
                data_temp.pop(i)
                continue

            # filter on build target
            if build_target != "":
                if build['buildtargetid'] is None:
                    if build['buildtargetid'] != build_target:
                        data_temp.pop(i)
                        continue
                else:
                    LOGGER.log(f"The buildtargetid was not detected", log_type=LogLevel.LOG_ERROR)
                    data_temp.pop(i)
                    continue

            # filter on platform
            if platform != "":
                if not build['platform'] is None:
                    if build['platform'] != platform:
                        # the platform is different: remove the build from the result
                        data_temp.pop(i)
                        continue
                else:
                    LOGGER.log(f"The platform was not detected", log_type=LogLevel.LOG_ERROR)
                    data_temp.pop(i)
                    continue

        final_data: List[Build] = list()
        for build in data_temp:
            build_primary = ''
            build_status = UCBBuildStatus.UNKNOWN
            build_finished = ''

            if 'buildStatus' in build:
                if build['buildStatus'] == 'success':
                    build_status = UCBBuildStatus.SUCCESS
                elif build['buildStatus'] == 'started':
                    build_status = UCBBuildStatus.STARTED
                elif build['buildStatus'] == 'queued':
                    build_status = UCBBuildStatus.QUEUED
                elif build['buildStatus'] == 'failure':
                    build_status = UCBBuildStatus.FAILURE
                elif build['buildStatus'] == 'canceled':
                    build_status = UCBBuildStatus.CANCELED
                elif build['buildStatus'] == 'restarted':
                    build_status = UCBBuildStatus.RESTARTED
                elif build['buildStatus'] == 'sentToBuilder':
                    build_status = UCBBuildStatus.SENTTOBUILDER

            if 'download_primary' in build['links']:
                build_primary = build['links']['download_primary']['href']

            if 'finished' in build:
                build_finished = build['finished']

            if 'build' not in build:
                continue

            if 'buildtargetid' not in build:
                continue

            if 'platform' not in build:
                continue

            build_obj = Build(number=build['build'], build_target_id=build['buildtargetid'], status=build_status,
                              date_finished=build_finished, download_link=build_primary, platform=build['platform'],
                              last_built_revision=build['lastBuiltRevision'], UCB_object=build)

            final_data.append(build_obj)

        final_data.sort(key=lambda item: item.number)

        return final_data

    def __get_all_builds__(self, build_target: str = "") -> List[Build]:
        url = '{}/buildtargets/_all/builds'.format(self.__api_url())
        response = requests.get(url, headers=self.__headers())

        data_temp = []

        if not response.ok:
            LOGGER.log(f"Getting build template failed: {response.text}", log_type=LogLevel.LOG_ERROR)
            return data_temp

        data = response.json()
        data_temp = copy.deepcopy(data)
        # let's filter the result on the requested branch only
        for i in reversed(range(0, len(data))):
            build = data[i]

            # identify if the build is successful
            if "build" not in build:
                # log(f"Missing build field for {build["build"]}", type=LOG_ERROR)
                data_temp.pop(i)
                continue

            # filter on build target
            if build_target != "":
                if build['buildtargetid'] is None:
                    if build['buildtargetid'] != build_target:
                        data_temp.pop(i)
                        continue
                else:
                    LOGGER.log(f"The buildtargetid was not detected", log_type=LogLevel.LOG_ERROR)
                    data_temp.pop(i)
                    continue

        final_data: List[Build] = list()
        for build in data_temp:
            build_primary = ''
            build_status = UCBBuildStatus.UNKNOWN
            build_finished = ''
            build_last_built_revision = ''

            if build['buildStatus'] == 'success':
                build_status = UCBBuildStatus.SUCCESS
            elif build['buildStatus'] == 'started':
                build_status = UCBBuildStatus.STARTED
            elif build['buildStatus'] == 'queued':
                build_status = UCBBuildStatus.QUEUED
            elif build['buildStatus'] == 'failure':
                build_status = UCBBuildStatus.FAILURE
            elif build['buildStatus'] == 'canceled':
                build_status = UCBBuildStatus.CANCELED
            elif build['buildStatus'] == 'restarted':
                build_status = UCBBuildStatus.RESTARTED
            elif build['buildStatus'] == 'sentToBuilder':
                build_status = UCBBuildStatus.SENTTOBUILDER

            if 'download_primary' in build['links']:
                build_primary = build['links']['download_primary']['href']

            if 'finished' in build:
                build_finished = build['finished']

            if 'lastBuiltRevision' in build:
                build_last_built_revision = build['lastBuiltRevision']

            build_obj = Build(number=build['build'], build_target_id=build['buildtargetid'], status=build_status,
                              date_finished=build_finished, download_link=build_primary, platform=build['platform'],
                              last_built_revision=build_last_built_revision, UCB_object=build)

            final_data.append(build_obj)

        final_data.sort(key=lambda item: item.number)

        return final_data

    def delete_build(self, build_target_id: str, build: int) -> bool:
        deleted = True
        url = '{}/artifacts/delete'.format(self.__api_url())

        data = {'builds': [{"buildtargetid": build_target_id, "build": build}]}

        response = requests.post(url, headers=self.__headers(), json=data)

        if not response.ok:
            deleted = False
            LOGGER.log(f"Deleting build target failed: {response.text}", log_type=LogLevel.LOG_ERROR)

        return deleted

    def display_builds_details(self) -> None:
        LOGGER.log(f" {len(self.builds_categorized['success'])} builds are successful and waiting for processing",
                   log_type=LogLevel.LOG_SUCCESS)
        if len(self.builds_categorized['building']) > 0:
            LOGGER.log(f" {len(self.builds_categorized['building'])} builds are building",
                       log_type=LogLevel.LOG_WARNING,
                       no_prefix=True)
        if len(self.builds_categorized['failure']) > 0:
            LOGGER.log(f" {len(self.builds_categorized['failure'])} builds are failed", log_type=LogLevel.LOG_ERROR,
                       no_prefix=True)
        if len(self.builds_categorized['canceled']) > 0:
            LOGGER.log(f" {len(self.builds_categorized['canceled'])} builds are canceled", log_type=LogLevel.LOG_ERROR,
                       no_prefix=True)
        if len(self.builds_categorized['unknown']) > 0:
            LOGGER.log(f" {len(self.builds_categorized['unknown'])} builds are in a unknown state",
                       log_type=LogLevel.LOG_WARNING,
                       no_prefix=True)

# endregion
