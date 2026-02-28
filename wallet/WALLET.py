from __future__ import annotations

from PW_UTILS.DIRECTORY import DIRECTORY
from WALLET_BASE import WALLET_BASE
from WALLET_MESSENGER import WALLET_MESSENGER
from WALLET_SESSIONS import WALLET_SESSIONS
from WALLET_SETUP import WALLET_SETUP
from WALLET_PROMPT import WALLET_PROMPT
from WALLET_BINDS import WALLET_BINDS
from WALLET_SHARE import WALLET_SHARE
from WALLET_PAY import WALLET_PAY
from PW_UTILS.UTILS import UTILS
from PW_UTILS.STRUCT import STRUCT


class WALLET(
    WALLET_SETUP, WALLET_SHARE, WALLET_BINDS, WALLET_SESSIONS, WALLET_PAY,
    WALLET_PROMPT, WALLET_MESSENGER, WALLET_BASE):
    

    @staticmethod
    def Reset():
        WALLET._wallet = None

    _wallet:WALLET = None


    @staticmethod
    def CreateWallet(domain:str):
        '''👉 Creates and onboards a wallet.'''
        wallet = WALLET()

        # Hook events.
        wallet.HandleEvents(
            translated= wallet.OnTranslated,
            sessionsUpdated= wallet.OnSessionUpdated,
            bindsUpdated = wallet.OnBindsUpdated,
            tokensUpdate = wallet.OnTokensUpdated,
            prompt= wallet.OnPrompt,
            goodbye = wallet.OnGoodbye,
            bindable= wallet.OnBindable,
            query= wallet.OnQuery,
            offer= wallet.OnOffer,
            charge= wallet.OnCharge
        )

        wallet.Setup(
            notifier= domain,
            language= 'en-us'
        )
        wallet.Onboard()
        wallet.Translate('en-us')

        WALLET._wallet = wallet


    @staticmethod
    def GetWallet():
        '''👉️ Get the singleton wallet instance.'''
        return WALLET._wallet
    

    @staticmethod
    def DumpToFile(dir:DIRECTORY = None):
        wallet = WALLET._wallet
        if wallet == None:
            return
        
        if dir == None:
            dir = UTILS.OS().CurrentDirectory().GetSubDir('__dumps__')
        file = dir.GetFile('WALLET.yaml')

        dump = STRUCT({
            'CONFIG': wallet._Config,
            'TOKENS': wallet._Tokens
        })
        yaml = dump.ToYaml()
        file.WriteText(yaml)