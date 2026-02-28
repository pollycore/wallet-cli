
from WALLET_MESSENGER import WALLET_MESSENGER
from PW_UTILS.UTILS import UTILS
from PW_UTILS.HANDLER import HANDLER


class WALLET_SETUP(WALLET_MESSENGER):
    '''👱📎 https://quip.com/u9H6AsA6azmA/-Wallet-Setup'''


    def Setup(self, notifier:str, language:str):
        '''👉 Creates the public/private key pair.'''

        UTILS.RequireArgs([notifier, language])

        # Set up the notifier and the language.
        self.RequireNotifier(set= notifier)
        self.RequireLanguage(set= language)

        # Get a public and private key.
        private, public, dkim = UTILS.CRYPTOGRAPHY().GenerateKeyPair()
        self.RequirePrivateKey(set= private)
        self.RequirePublicKey(set= public)
        self.RequireDKIM(set= dkim)


    def Onboard(self):
        ''' 👉 Gets a WalletID from the Broker.
        * https://quip.com/u9H6AsA6azmA#temp:C:aXG191738dd4065486f9c632656b'''
        onboarded = self.CallNotifier(
            subject= 'Onboard@Notifier',
            body= {
                'Language': self.RequireLanguage(),
                'PublicKey': self.RequireDKIM()
            })

        self.RequireWalletID(set= onboarded.RequireStr('WalletID'))
        self.RequireBroker(set= onboarded.RequireStr('Broker'))
        self.RequireGraph(set= onboarded.RequireStr('Graph'))


    def SetWebSocket(self):
        '''👉 Sets up the sockets.'''
        self.CallNotifier(
            subject= 'SetWebSocket@Notifier',
            body= {
                'WalletID': self.RequireWalletID(),
                'Broker': self.RequireBroker(),
                'WebSocketID': "<socket-id>"
            })


    def SetPushNotications(self):
        '''👉 Sets up the push notifications.'''
        self.CallNotifier(
            subject= 'SetPushNotications@Notifier',
            body= {
                'WalletID': self.RequireWalletID(),
                'Broker': self.RequireBroker(),
                "Engine": 'ANDROID',
                "TokenID": "<token-id>"
            })


    def Translate(self, language:str):
        '''👉 Translates Sessions, Binds, and Tokens.
        * https://quip.com/u9H6AsA6azmA#temp:C:aXGd01a597ee468481d9af56aa02'''
        self.CallBroker(
            subject= 'Translate', 
            body= {
                "Language": language 
            })


    @classmethod
    def TriggerOnTranslate(cls, handler:HANDLER, language:str):
        handler.Trigger(
            event= 'OnTranslated@Notifier', 
            args= language)


    def OnTranslated(self, language:str):
        '''👉 Result from a translation.'''
        self.RequireLanguage(set=language)