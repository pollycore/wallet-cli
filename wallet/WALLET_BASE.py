from PW_UTILS.STRUCT import STRUCT


class WALLET_BASE():


    def __init__(self) -> None:
        self._Config = STRUCT({})


    def SetChat(self, set:any=None) -> None:
        from CHAT import CHAT
        CHAT.AssertClass(set)
        self._chat:CHAT = set
    

    def GetChat(self, set:any=None):
        from CHAT import CHAT
        CHAT.AssertClass(set)
        CHAT.AssertClass(self._chat)
        return self._chat


    def RequireWalletID(self, set:str=None) -> str:
        return self._Config.RequireStr('WalletID', set=set)


    def RequireGraph(self, set:set=None) -> str:
        return self._Config.RequireStr('Graph', set=set)
    

    def RequireNotifier(self, set:str=None) -> str:
        return self._Config.RequireStr('Notifier', set=set, default='any-notifier.org')
    
    
    def RequireBroker(self, set:str=None) -> str:
        return self._Config.RequireStr('Broker', set=set)
    
    
    def RequireLanguage(self, set:str=None) -> str:
        return self._Config.RequireStr('Language', set=set, default='en-us')
    

    def RequirePrivateKey(self, set:str=None):
        return self._Config.RequireStr('PrivateKey', set=set)
    

    def RequirePublicKey(self, set:str=None):
        return self._Config.RequireStr('PublicKey', set=set)
    

    def RequireDKIM(self, set:str=None):
        return self._Config.RequireStr('DKIM', set=set)
    