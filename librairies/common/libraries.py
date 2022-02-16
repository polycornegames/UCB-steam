from typing import Optional, Dict

from botocore.exceptions import ClientError

from librairies import Config, LOGGER
from librairies.UCB.classes import BuildTarget
from librairies.aws import PolyAWSDynamoDB
from librairies.common.classes import Package
from librairies.logger import LogLevel


# region FILE
def replace_in_file(file, haystack, needle):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # replace all occurrences of the required string
    data = data.replace(str(haystack), str(needle))
    # close the input file
    fin.close()
    # open the input file in write mode
    fin = open(file, "wt")
    # override the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def write_in_file(file, data):
    # open the input file in write mode
    fin = open(file, "wt")
    # override the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def read_from_file(file):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # close the input file
    fin.close()
    return data


# endregion

# region PACKAGES
def load_packages_config(config: Config, environments=None) -> Optional[Dict[str, Package]]:
    if environments is None:
        environments = []

    try:
        aws_dynamo_db: PolyAWSDynamoDB = PolyAWSDynamoDB(aws_region=config.settings['aws']['region'],
                                                         dynamodb_table=config.settings['aws']['dynamodbtable'])
        package_data = aws_dynamo_db.get_packages_data()
    except ClientError as e:
        print(e.response['Error']['Message'])
        return None

    packages: Dict[str, Package] = dict()
    for build_target in package_data:
        # region STORES
        if 'stores' in build_target:
            for store_name in build_target['stores']:
                if 'package' in build_target['stores'][store_name]:
                    package_name = build_target['stores'][store_name]['package']

                    # filter only on wanted packages (see arguments)
                    wanted_package: bool = False
                    if len(environments) == 0:
                        wanted_package = True
                    else:
                        for environment in environments:
                            if package_name == environment:
                                wanted_package = True
                                break

                    if wanted_package:
                        # package is not already part of the list ? create it
                        if package_name not in packages:
                            package = Package(name=package_name)
                            packages[package_name] = package
                        else:
                            package = packages[package_name]

                        # store is not already part of the package list ? add it
                        store_exists: bool = True
                        if not package.contains_store(store_name):
                            if store_name in config.store_plugins.keys():
                                package.add_store(config.store_plugins[store_name])
                            else:
                                store_exists = False

                        # if the store plugin exists, continue
                        if store_exists:
                            # region BuildTarget creation
                            build_target_obj = BuildTarget(name=build_target['id'])
                            for parameter, value in build_target['stores'][store_name].items():
                                if parameter != 'package':
                                    build_target_obj.parameters[parameter] = value
                            # endregion

                            packages[package_name].add_build_target_to_store(store_name, build_target_obj)
                        else:
                            LOGGER.log(f'Store plugin {store_name} does not exists', log_type=LogLevel.LOG_WARNING)
        # endregion

        # region HOOKS
        if 'hooks' in build_target:
            for hook_name in build_target['hooks']:
                if 'package' in build_target['hooks'][hook_name]:
                    package_name = build_target['hooks'][hook_name]['package']

                    # filter only on wanted packages (see arguments)
                    wanted_package: bool = False
                    if len(environments) == 0:
                        wanted_package = True
                    else:
                        for environment in environments:
                            if package_name == environment:
                                wanted_package = True
                                break

                    if wanted_package:
                        # package is not already part of the list ? create it
                        if package_name not in packages:
                            package = Package(name=package_name)
                            packages[package_name] = package
                        else:
                            package = packages[package_name]

                        # hook is not already part of the package list ? add it
                        hook_exists: bool = True
                        if not package.contains_store(hook_name):
                            if hook_name in config.hook_plugins.keys():
                                package.add_hook(config.hook_plugins[hook_name])
                            else:
                                hook_exists = False

                        # if the hook plugin exists, continue
                        if hook_exists:
                            # region BuildTarget creation
                            build_target_obj = BuildTarget(name=build_target['id'])
                            for parameter, value in build_target['hooks'][hook_name].items():
                                if parameter != 'package':
                                    build_target_obj.parameters[parameter] = value
                            # endregion

                            packages[package_name].add_build_target_to_hook(hook_name,
                                                                            build_target_obj)
                        else:
                            LOGGER.log(f'Hook plugin {hook_name} does not exists', log_type=LogLevel.LOG_WARNING)
        # endregion

    for package_name, package in packages.items():
        packages[package_name].stores = dict(sorted(package.stores.items()))
        packages[package_name].hooks = dict(sorted(package.hooks.items()))
    return packages
# endregion
