from PW_UTILS.HANDLER import HANDLER
from PW import PW
from PROMPT_SESSION import PROMPT_SESSION
from WALLET_TOKENS import WALLET_TOKENS
from WALLET_MESSENGER import WALLET_MESSENGER
from QUERY import BROKER_QUERY
from PW_UTILS.UTILS import UTILS
from CHAT_LINE import CHAT_LINE
from PW_UTILS.LOG import LOG


class WALLET_SHARE(WALLET_TOKENS, WALLET_MESSENGER):
    '''👱📎 https://quip.com/j1F4AEIUhMyP/-Wallet-Share'''
    

    @classmethod
    def TriggerOnQuery(cls, handler:HANDLER, session:PROMPT_SESSION, query:BROKER_QUERY, domain:str):
        handler.TriggerPython('OnQuery@Notifier', session, query, domain)

    
    def _verifyScriptVsQuery(self, query:BROKER_QUERY, line:CHAT_LINE):
        LOG.Print(f'👱🧠 WALLET_SHARE._verifyScriptVsQuery()',
                  'query=', query,
                  'line=', line)
        
        UTILS.RequireArgs([query, line])
        
        # From the Broker's message, get all bounds flattened.
        brokerCode = query.RequireCode()
        brokerVaults = [f'{brokerCode}@{bind.RequireStr("Vault")}' for bind in query.RequireBinds()]
        brokerIssuers = [f'{brokerCode}@{bind.RequireStr("Issuer")}' for bind in query.RequireTokens()]

        # From the script, get all queries flattened.
        scriptCode = line.RequireCode()
        scriptVaults = [f'{scriptCode}@{vault}' for vault in line.GetVaults()]
        scripIssuers:list[str] = [f'{scriptCode}@{issuer}' for issuer in line.GetIssuers()]
        
        # Check if all broker-info is in script-info.
        for pair in brokerVaults:
            if pair not in scriptVaults:
                line.Parent().Raise(
                    f'Unexpected code/vault ({pair=}) was received by the broker, '\
                    f'but was not expected by the script!\n {brokerVaults=},\n {scriptVaults=}')
        for pair in brokerIssuers:
            if pair not in scripIssuers:
                line.Parent().Raise(
                    f'Unexpected code/issuer ({pair=}) was received by the broker, '\
                    f'but was not expected by the script!\n {brokerIssuers=},\n {scripIssuers=}', 
                    source= line)
                
        # Check if all script-queries are in broker-bounds.
        for pair in scriptVaults:
            if pair not in brokerVaults:
                line.Parent().Raise('Missing bound bind!:' + pair)
        for pair in scripIssuers:
            if pair not in brokerIssuers:
                line.Parent().Raise('Missing bound token!:' + pair)


    def OnQuery(self, session:PROMPT_SESSION, query:BROKER_QUERY, domain:str):
        '''👉 Receives the bindable list from a Vault, and binds a few codes.'''
        LOG.Print(f'🤵➡️👱 WALLET_SHARE.OnQuery()', 
                  'query=', query)

        # ==============================
        # VALIDATIONS
        # ==============================

        # Required arguments.
        UTILS.RequireArgs([session, query])

        # Integrity of entities.
        session.VerifySession()
        query.VerifyBrokerQuery()

        # Script line to execute.
        chat = self.GetChat()
        line = chat.OnWalletLine(
            format= 'SHARE',
            session= session,
            source= query,
            domain= domain)
        
        # Script line integrity.
        line.MatchQuery(query= query)

        # Request math against what the script was expecting.
        self._verifyScriptVsQuery(
            query=query,
            line=line)
        
        # ==============================
        # Coherence on the result of the script.
        # ==============================

        disclose = line.GetDisclose()
        verify = line.GetVerify()

        # If not sharing, don't add a Share section.
        if line.GetAnswer() in ['NO', 'CANCEL']:
            if disclose!=None or verify!=None:
                chat.Raise('Not allowed: disclose and verify should not exist when Answer=NO!')

        # Something needs to be shared.
        elif UTILS.IsNoneOrEmpty(disclose) and UTILS.IsNoneOrEmpty(verify):
            chat.Raise('Missing: 🤔 did you forget to share? or say Answer=NO?', source=line)

        # Either disclose or Verify - both cannot exist.
        elif disclose!=None and verify!=None:
            chat.Raise('Not allowed: should either to Disclose() or Verity(), not both.')
        
        # ==============================
        # EXECUTION
        # ==============================

        # Stop the conversation.
        if line.GetAnswer() in ['CANCEL']:
            return 
        
        # Won't share anything with the consumer (because doesn't want to, or doesn't have).
        if line.GetAnswer() in ['NO']:
            return PW.ROLES().CONSUMER().InvokeWontShare(
                session= session, 
                code= query.RequireCode())
                        
        # Ask the vault to disclose the information.
        elif not UTILS.IsNoneOrEmpty(disclose):
            vault = disclose
            bind = query.RequireBind(vault)

            return PW.ROLES().VAULT().InvokeDisclose(
                session= session,
                vault= vault,
                bindID= bind.RequireStr('BindID'),
                language= self.RequireLanguage())
        
        # Send the token directly to the consumer.
        elif not UTILS.IsNoneOrEmpty(verify):
            tokens = []

            for c in query.RequireTokens():

                # Discard if not from the selected issuer.
                issuer= c.RequireStr('Issuer')
                if verify != issuer:
                    continue

                # Create the token information.
                token = PW.INTERFACES().TOKEN().New(
                    tokenID= c.RequireUUID('TokenID'),
                    issuer= issuer,
                    code= query.RequireCode(),
                    version= c.RequireStr('Version'),
                    qr= self.GetToken(c.RequireStr('Path')),
                    starts= c.RequireStr('Starts'),
                    expires= c.RequireStr('Starts'))
                
                # Check the integrity.
                token.VerifyToken()

                # Add to the return list.
                tokens.append(token)

            # Verify if there is one and only one.
            UTILS.AssertLenght(
                tokens, expectedLength=1, 
                msg='There should only be 1 token for the code/issuer to verify.') 
            
            # Send it to the consumer.
            PW.ROLES().CONSUMER().InvokeVerify(
                session= session,
                tokens= tokens)
            
        else:
            chat.Raise('Unexpected behaviour: not rejected, disclosed, or verified')
           