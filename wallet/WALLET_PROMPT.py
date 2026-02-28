from PROMPT_SESSION import PROMPT_SESSION
from PROMPT_REPLY import PROMPT_REPLY
from WALLET_MESSENGER import WALLET_MESSENGER
from PW import PW
from PW_UTILS.HANDLER import HANDLER
from PW_UTILS.LOG import LOG


class WALLET_PROMPT(WALLET_MESSENGER):
    '''👱📎 https://quip.com/GKnaA9waat3i/-Wallet-Prompt'''


    @classmethod
    def TriggerOnPrompt(cls, 
        handler:HANDLER, 
        session:PROMPT_SESSION, 
        promptID:str, 
        sender:str):

        LOG.Print('📣👱 WALLET.PROMPT.TriggerOnPrompt()')
        handler.TriggerPython('OnPrompt@Notifier', session, promptID, sender)


    def OnPrompt(self, session:PROMPT_SESSION, promptID:str, sender:str):
        LOG.Print(
            '📣👱 WALLET.PROMPT.OnPrompt()',
            f'{sender=}',f'{promptID=}',
            'session=', session)

        prompt = PW.ROLES().HOST().InvokePrompted(
            host= sender, 
            sessionID= session.RequireSessionID(),
            promptID= promptID)

        # Validations.
        prompt.VerifyPrompt()
        format = prompt.RequireFormat()
        line = self.GetChat().OnWalletLine(
            format= format,
            session= session, 
            source= prompt,
            domain= sender)
        line.MatchPrompt(prompt)

        if format == 'SELFIE':
            # Open an iFrame with the URL of the appendix.
            PW.ROLES().SELFIE_SUPPLIER().MockHandleOrder(
                url= prompt.RequireLocator())
            return

        elif format == 'TOUCH':
            # Touch the locator.
            PW.ROLES().EPHEMERAL_BUYER().MockInvokeTouched(
                locator= prompt.RequireLocator(),
                session= session.ToInterface())
            return
        
        elif format == 'WAIT':
            # Just wait 😌
            return 

        # Compile.
        if format in ['INT', 'RATE']:
            answer = line.RequireAnswer()
        else:
            answer = line.GetAnswer()
        
        if answer == 'CANCEL': result = 'CANCEL' 
        elif answer == 'YES': result = 'YES' 
        elif answer == 'NO': result = 'NO' 
        else: result = 'OK'

        reply = PROMPT_REPLY.Reply(
            prompt= prompt,
            result= result,
            answer= line.GetAnswer())
        reply.VerifyReply()

        # Invoke.
        PW.ROLES().HOST().InvokeReply(
            session= session,
            reply= reply,
            domain= sender)
        

    @classmethod
    def TriggerOnGoodbye(cls, 
        handler:HANDLER, session:PROMPT_SESSION, message:str, domain:str):

        handler.TriggerPython(
            'OnGoodbye@Notifier', session, message, domain)


    def OnGoodbye(self, session:PROMPT_SESSION, message:str, domain:str):
        LOG.Print('📣👱 WALLET.PROMPT.OnGoodbye()', f'{message=}')

        # Validations.
        line = self.GetChat().OnWalletLine(
            format= 'GOODBYE',
            session= session, 
            source= 'OnGoodbye@Wallet',
            domain= domain)
        line.MatchGoodbye(message=message)