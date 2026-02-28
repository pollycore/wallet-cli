from PW_UTILS.HANDLER import HANDLER
from BROKER_TOKEN import BROKER_TOKEN
from PW import PW
from PROMPT_SESSION import PROMPT_SESSION
from WALLET_MESSENGER import WALLET_MESSENGER
from PW_UTILS.UTILS import UTILS


class WALLET_TOKENS(WALLET_MESSENGER):
    '''👱📎 https://quip.com/YdJpA3idWduO/-Wallet-Tokens'''
    

    # ==================================
    # IN-MEMORY TOKEN STORE
    # ==================================


    # In-memory storage, for testing purposes.
    _Tokens = {}

    def GetToken(self, path:str) -> str:
        UTILS.Require(path)
        UTILS.AssertIsType(path, str)
        return WALLET_TOKENS._Tokens[path]
    
    def AddToken(self, path:str, qr:str) -> None:
        UTILS.Require(qr)
        UTILS.AssertIsType(qr, str)
        WALLET_TOKENS._Tokens[path] = qr
    
    def RemoveToken(self, path:str) -> None:
        UTILS.Require(path)
        UTILS.AssertIsType(path, str)
        del WALLET_TOKENS._Tokens[path]


    # ==================================
    # LOGIC
    # ==================================


    @classmethod
    def TriggerOnOffer(cls, handler:HANDLER, session:PROMPT_SESSION, token:BROKER_TOKEN, domain:str):
        handler.TriggerPython('OnOffer@Notifier', session, token, domain)

     
    def OnOffer(self, session:PROMPT_SESSION, token:BROKER_TOKEN, domain:str):
        '''🤵 Offer: https://quip.com/PCunAKUqSObO#temp:C:UKE43477024fb334f3c9bb85c34e '''
        '''👱 Accept:  https://quip.com/YdJpA3idWduO#temp:C:afPf2204358162a42529b4a902e9'''
        
        UTILS.AssertIsType(session, PROMPT_SESSION)
        UTILS.AssertIsType(token, BROKER_TOKEN)

        # Validations.
        line = self.GetChat().OnWalletLine(
            format= 'ISSUE',
            session= session, 
            source= token,
            domain= domain)
        line.MatchOffer(
            code = token.RequireCode())

        # Get the details from the token.
        issuer = token.RequireIssuer()
        tokenID = token.RequireTokenID()
        
        # 🃏🚀 Download the token QR from the Issuer.
        content = PW.ROLES().ISSUER().InvokeToken(
            issuer= issuer,
            tokenID= tokenID,
            sessionID= session.RequireSessionID())

        # Store the token QR locally.
        path = UTILS.UUID()
        self.AddToken(
            path= path, 
            qr= content)

        # 🤵🐌 Inform the Broker.
        self.CallBroker(
            subject= 'Accepted',
            body= {
                "SessionID": session.RequireSessionID(),
                "Issuer": issuer,
                "TokenID": tokenID,
                "Path": path
            })


    def OnTokensUpdated(self, request) -> None:
        self.ListTokens()
        

    def ListTokens(self):
        '''👱 https://quip.com/YdJpA3idWduO#temp:C:afP26be7d414fde4051ad1f8bc9a'''
        
        # 🤵🚀 Get the list.
        tokens = self.CallBroker('Tokens')
        
        # Show on screen.
        tokens.Print(
            title= 'Tokens'
        )


    def Remove(self, issuer:str, tokenID:str, path:str):
        '''👱 https://quip.com/YdJpA3idWduO#temp:C:afP374a396928444801a3ea04e7d'''
        
        # 🤵🐌 Remove from Broker.
        PW.ROLES().BROKER().InvokeRemove(
            issuer= issuer,
            tokenID= tokenID
        )

        # Remove locally
        self.RemoveToken(path)


    def ShowQR(self):
        '''👱 https://quip.com/YdJpA3idWduO#temp:C:afPd79f5aa42a8c4228872b1fbfa'''
        pass


    def CheckIn(self):
        '''👱 https://quip.com/YdJpA3idWduO#temp:C:afP1b008054800145c18b83f3ffc'''
        pass

