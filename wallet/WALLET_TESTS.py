from WALLET import WALLET
from PW_AWS.AWS_TEST import AWS_TEST
from PW_UTILS.LOG import LOG

class WALLET_TESTS(WALLET, AWS_TEST):

    
    @classmethod
    def TestAllWallet(cls):
        LOG.Print('WALLET_TESTS.TestAllWallet() ==============================')
        
        cls.ResetAWS()
        cls.MOCKS().NOTIFIER().MockNotifier()

        wallet = WALLET()
        wallet.Setup(
            notifier= 'any-notifier.org',
            language= 'en-us')
        
        wallet.Onboard()
        wallet.SetWebSocket()
        wallet.SetPushNotications()

        wallet.Translate('pt-br')

        wallet.ListSessions()

        wallet.ListBinds()

        wallet.ListTokens()

        '''
        wallet.OnQuery(
            session= cls.MOCKS().BROKER().MockSession(),
            message= '<query-message>',
            bound= [],
            unbound= []
        )
        '''