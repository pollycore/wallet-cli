from PW import PW
from PW_UTILS.STRUCT import STRUCT
from WALLET_MESSENGER import WALLET_MESSENGER
from PROMPT_SESSION import PROMPT_SESSION
from PW_UTILS.HANDLER import HANDLER
from PW_UTILS.LOG import LOG


class WALLET_BINDS(WALLET_MESSENGER):
    '''👱📎 https://quip.com/b8a0AHaXf3C6/-Wallet-Binds'''

    
    @classmethod
    def TriggerOnBindable(cls, handler:HANDLER, session:PROMPT_SESSION, bindable:list[STRUCT], domain:str):
        handler.TriggerPython('OnBindable@Notifier', session, bindable, domain)


    def OnBindable(self, session:PROMPT_SESSION, bindable:list[STRUCT], domain:str):
        '''👉 Receives the bindable list from a Vault, and binds a few codes.
        * 🗄️ https://quip.com/IZapAfPZPnOD#temp:C:PDZe58aeffc2fb64a76a0f16ac38
        * 🤵 https://quip.com/oSzpA7HRICjq#temp:C:DSD2aa2718d92bf4941ac7bb41e9
        * 📣 https://quip.com/PCunAKUqSObO#temp:C:UKEe59fd4b4d73345348afd67d5f
        * 👱 https://quip.com/b8a0AHaXf3C6/-Wallet-Binds#temp:C:DPS9f5401c512ad42d89656f6b4e
        '''

        LOG.Print(f'🤵➡️👱 WALLET_BINDS.OnBindable()')
                  
        # Validations.
        line = self.GetChat().OnWalletLine(
            format= 'BINDABLE',
            session= session,
            source= bindable,
            domain= domain)
        
        line.MatchBindable(
            bindable = [ 
                code.RequireStr('Code') 
                for code in bindable 
            ])

        # Execution.
        if line.GetAnswer() != 'CANCEL':
            # Otherwise, bind.
            return PW.ROLES().BROKER().InvokeBind(
                sessionID= session.RequireSessionID(),
                codes= line.RequireBindList())


    def OnBindsUpdated(self, request) -> None:
        LOG.Print(f'🤵➡️👱 WALLET.OnBindsUpdated()')
        self.ListBinds()


    def ListBinds(self) -> None:
        binds = self.CallBroker('Binds')
        binds.Print('Binds')
        ##LOG.Exception('Find the missing bind')