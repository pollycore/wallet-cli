from PW_UTILS.UTILS import UTILS
from MSG import MSG
from PW import PW
from PW_UTILS.STRUCT import STRUCT
from WALLET_BASE import WALLET_BASE


class WALLET_MESSENGER(WALLET_BASE):
    '''👱📎 https://quip.com/UfRaAJPZ4CqH/-Wallet-Messenger'''


    def CallNotifier(self, subject:str, body:any={}) -> STRUCT:
        if '@' not in subject:
            subject = subject + '@Notifier'

        return self.CallDomain(
            domain= self.RequireNotifier(),
            subject= subject, 
            body= body)


    def CallBroker(self, subject:str, body:any={}) -> STRUCT:
        UTILS.RequireArgs([subject])
        UTILS.AssertIsType(subject, str)

        if '@' not in subject:
            subject = subject + '@Broker'

        return self.CallDomain(
            domain= self.RequireBroker(),
            subject= subject, 
            body= body)

    
    def CallDomain(self, domain:str, subject:str, body:any) -> STRUCT:
        '''👉 https://quip.com/UfRaAJPZ4CqH/-Wallet-Messenger#temp:C:MGV00bd1367bf03441fbc55c4b78'''

        ##LOG.Print(f'\nCallDomain(domain={domain}, subject={subject}, body=...)')
        ##LOG.Print(f'  CallDomain(): {self.RequireNotifier()=}')
        
        # Wrap the body in a message.
        msg = MSG.Wrap(
            to= domain,
            subject= subject,
            body= body)

        # Set the destination...
        if domain == self.RequireNotifier() \
        and subject in ['Onboard@Notifier']:
            # before onboarding, there's no ID - that's OK.
            msg.RequireFrom('Anonymous')

        elif domain in [self.RequireBroker(), self.RequireNotifier()]:
            # for the broker and notifier, send the wallet ID.
            msg.RequireFrom(self.RequireWalletID())
            
        else:
            # otherwise, hide behind the broker.
            msg.RequireFrom(self.RequireBroker())

        # Sign the message.
        if msg.RequireFrom() == 'Anonymous':
            msg.Sign('Anonymous', 'Anonymous')
        else:
            PW.BEHAVIORS().SYNCAPI().SENDER().SignMsg(
                privateKey= self.RequirePrivateKey(),
                publicKey= self.RequirePublicKey(),
                msg= msg)

        # Send the message.
        response = msg.Send()

        return STRUCT(response)


    def HandleEvent(self, event:str, handler:object):
        '''👉 Registers a handler for a python event.'''
        if '@' not in event:
            event = event + '@Notifier'
        PW.ROLES().NOTIFIER().OnPython(
            event= event,
            handler= handler
        )


    def HandleEvents(
            self, 
            translated: object=None,
            sessionsUpdated: object=None,
            bindsUpdated: object=None,
            tokensUpdate: object=None,
            prompt: object=None, 
            goodbye: object=None,
            bindable: object=None,
            query: object=None,
            offer: object=None,
            charge: object=None
            ):
        '''👉 Registers handlers for python events.'''

        handlers = {
            'OnTranslated': translated,
            'OnSessionsUpdated': sessionsUpdated,
            'OnBindsUpdated': bindsUpdated,
            'OnTokensUpdated': tokensUpdate,
            'OnPrompt': prompt,
            'OnGoodbye': goodbye,
            'OnBindable': bindable,
            'OnQuery': query,
            'OnOffer': offer,
            'OnCharge': charge
        }

        for event in handlers.keys():
            handler = handlers[event]
            if handler != None:
                self.HandleEvent(
                    event= event,
                    handler= handler
                )