import os
import sys
from typing import Dict

import yaml

from librairies import LOGGER
from librairies.UCB.classes import BuildTarget
from librairies.hook import Hook
from librairies.libraries import PolyBitBucket
from librairies.logger import LogLevel
from librairies.stores import Store


class BitBucketHook(Hook):
    bitbucket_connection: PolyBitBucket

    def __init__(self, base_path: str, home_path: str, parameters: yaml.Node, notified: bool = False):
        super().__init__(base_path, home_path, parameters, notified)
        self.name = "bitbucket"

        self.username: str = self.parameters['bitbucket']['username']
        self.app_password: str = self.parameters['bitbucket']['app_password']
        self.workspace: str = self.parameters['bitbucket']['workspace']
        self.repository: str = self.parameters['bitbucket']['repository']

    def notify(self, build_target: BuildTarget, simulate: bool = False):
        self.bitbucket_connection = PolyBitBucket(bitbucket_username=self.username,
                                                  bitbucket_app_password=self.app_password,
                                                  bitbucket_cloud=True,
                                                  bitbucket_workspace=self.workspace,
                                                  bitbucket_repository=self.repository)

        self.bitbucket_connection.trigger_pipeline(
            build_target.parameters['branch'],
            build_target.parameters['pipeline'])
