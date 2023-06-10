from typing import Optional, Final, List

from discord_webhook import DiscordWebhook, DiscordEmbed
from requests import Response

from libraries import LOGGER
from libraries.Unity.classes import BuildTarget
from libraries.hook import Hook
from libraries.logger import LogLevel

# region ERRORS NUMBER
# must be over 10000
DISCORD_CONNECTION_FAILED: Final[int] = 10901
DISCORD_NOTIFICATION_FAILED: Final[int] = 10902
DISCORD_CONNECTION_TEST_FAILED: Final[int] = 10903
DISCORD_NOTIFICATION_TEST_FAILED: Final[int] = 10904


# endregion

class PolyDiscord:
    def __init__(self, discord_webhook_url: str):
        self._discord_webhook_url: str = discord_webhook_url
        self._discord_connection: Optional[DiscordWebhook] = None

    @property
    def discord_webhook_url(self):
        return self._discord_webhook_url

    def send_message(self, content: str) -> bool:
        try:
            self._discord_connection = DiscordWebhook(url=self._discord_webhook_url, content=content)
            response: Response = self._discord_connection.execute()

            if response.status_code != 200:
                return False
        except Exception as e:
            return False

        return True

    def send_embed(self, title: str, description: str, color: str, footer: str) -> bool:
        try:
            self._discord_connection = DiscordWebhook(url=self._discord_webhook_url)

            # create embed object for webhook
            embed: DiscordEmbed = DiscordEmbed(title=title, description=description, color=color)

            # set author
            # embed.set_author(name=author)

            # set image
            # embed.set_image(url='your image url')

            # set thumbnail
            # embed.set_thumbnail(url='your thumbnail url')

            # set footer
            embed.set_footer(text=footer)

            # set timestamp (default is now)
            embed.set_timestamp()

            # add fields to embed
            # embed.add_embed_field(name='Field 1', value='Lorem ipsum')
            # embed.add_embed_field(name='Field 2', value='dolor sit')

            # add embed object to webhook
            self._discord_connection.add_embed(embed)

            response: Response = self._discord_connection.execute()

            if response.status_code != 200:
                return False

        except Exception as e:
            return False

        return True


class DiscordHook(Hook):
    def __init__(self, base_path: str, home_path: str, parameters: dict, notified: bool = False):
        super().__init__(base_path, home_path, parameters, notified)
        self._already_notified_build_target: List[str] = list()
        self.name = "discord"

        if 'discord' not in self.parameters.keys():
            return

        if 'webhook_url' not in self.parameters['discord'].keys():
            LOGGER.log("'discord' configuration file section have no 'webhook_url' value", log_type=LogLevel.LOG_ERROR)
            return

        self.webhook_url: str = self.parameters['discord']['webhook_url']

        if 'enabled' in self.parameters[self.name].keys():
            self.enabled = self.parameters[self.name]['enabled']

    def install(self, simulate: bool = False) -> int:
        pass

    def test(self) -> int:
        LOGGER.log("Testing Discord connection...", end="")
        DISCORD: PolyDiscord = PolyDiscord(discord_webhook_url=self.webhook_url)

        if not DISCORD.send_message(content="this is a test message"):
            return DISCORD_NOTIFICATION_TEST_FAILED

        if not DISCORD.send_embed(title="UCB Steam test embed",
                                  description="This is a test embed", color="F8C107",
                                  footer="Sent by UCB-Steam script"):
            LOGGER.log("Error connecting to Discord", log_type=LogLevel.LOG_ERROR, no_date=True)
            return DISCORD_NOTIFICATION_TEST_FAILED

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0

    def notify(self, build_target: BuildTarget, simulate: bool = False) -> int:
        LOGGER.log(f"  Notifying {self.name} for [{build_target.name}]...", end="")
        ok: bool = False

        if build_target.name not in self._already_notified_build_target:
            self._already_notified_build_target.append(build_target.name)

            if not simulate:
                DISCORD: PolyDiscord = PolyDiscord(discord_webhook_url=self.webhook_url)
                color: str = "00C400"
                # if not build_target.uploaded:
                #    color = "B00000"

                content: str = f"Build **{build_target.name}** has been successfully uploaded to:\r\n"
                for store_name in build_target.processed_stores.keys():
                    if build_target.processed_stores[store_name]:
                        content = content + f"- {store_name}: success\r\n"
                    else:
                        content = content + f"- {store_name}: failed\r\n"

                ok = DISCORD.send_embed(title="", description=content, color=color,
                                        footer="Sent by UCB-Steam script")

                if not ok:
                    return DISCORD_NOTIFICATION_FAILED

            build_target.notified = True

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0
