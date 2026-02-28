from QR import QR
from WALLET_MESSENGER import WALLET_MESSENGER


class WALLET_SESSIONS(WALLET_MESSENGER):
    '''👱📎 https://quip.com/7uakAJb60qfH/-Wallet-Sessions'''


    def Assess(self, qr:QR) -> None:
        '''👉 https://quip.com/7uakAJb60qfH#temp:C:XHZ2cf00e17b58a4659a3194887a
        Example: 🤝nlweb.org/QR,1,any-hairdresser.com,7V8KD3G'''

        QR.AssertClass(qr)
        self.CallBroker(
            subject= 'Assess',
            body= { 
                "QR": qr.RequireQR() 
            })


    def OnSessionUpdated(self, request) -> None:
        self.ListSessions()


    def ListSessions(self) -> None:
        '''👉 https://quip.com/7uakAJb60qfH#temp:C:XHZ1b34152afbfc40c8a02f4ccfd'''
        sessions = self.CallBroker(subject= 'Sessions')
        sessions.Print('Sessions')

    