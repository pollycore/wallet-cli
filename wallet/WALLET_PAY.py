from CHARGE import CHARGE,CHARGE_OPTION,CHARGE_OPTIONS

from PW_UTILS.HANDLER import HANDLER
from PROMPT_SESSION import PROMPT_SESSION
from WALLET_MESSENGER import WALLET_MESSENGER
from PW import PW
from PW_UTILS.LOG import LOG
from PW_UTILS.UTILS import UTILS


class WALLET_PAY(WALLET_MESSENGER):
    '''👱📎 https://quip.com/DTxiAOxqHsIx/-Wallet-Pay'''
    
    
    @classmethod
    def TriggerOnCharge(cls, 
                        handler:HANDLER, 
                        session:PROMPT_SESSION, 
                        message:str,
                        charge:CHARGE,
                        options:CHARGE_OPTIONS,
                        domain:str):
        
        handler.TriggerPython(
            'OnCharge@Notifier', 
            session, message, charge, options, domain)
    

    def OnCharge(self, 
                 session:PROMPT_SESSION, 
                 message:str,
                 charge:CHARGE,
                 options:CHARGE_OPTIONS, 
                 domain:str):
        
        '''👉 Receives the bindable list from a Vault, and binds a few codes.'''
        LOG.Print(f'🤵➡️👱 WALLET_SHARE.OnCharge()', 
                  f'{message=}',
                  'options=', options,
                  'charge=', charge,
                  'session=', session)

        # ==============================
        # VALIDATIONS
        # ==============================

        # Required arguments.
        UTILS.RequireArgs([session, message, charge, options, domain])

        # Integrity of entities.
        UTILS.AssertIsType(session, PROMPT_SESSION)
        session.VerifySession()

        UTILS.AssertIsType(charge, CHARGE)
        charge.VerifyCharge()

        UTILS.AssertIsType(options, CHARGE_OPTIONS)
        options.VerifyChargeOptions()

        # Script line to execute.
        chat = self.GetChat()
        line = chat.OnWalletLine(
            format= 'CHARGE',
            session= session,
            source= charge, 
            domain= domain)
        
        line.MatchCharge(
            charge= charge, 
            message= message)
                
        # ==============================
        # EXECUTION
        # ==============================

        payer = line.RequireAnswer()
        option = options.RequireOption(payer=payer)
        
        return PW.ROLES().PAYER().InvokeEndorse(
            source= 'OnCharge@Wallet',
            payer= payer,
            bindID= option.RequireBindID(),
            collector= option.RequireCollector(),
            session= session.ToInterface(),
            charge= charge)
    
        