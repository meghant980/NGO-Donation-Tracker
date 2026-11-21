NGO Donation Tracker - Virtual QR Demo Payment

The QR opens a web-based virtual payment page. Scan using any phone camera,
then press Pay (Demo only). It records a simulated payment status in SQLite.
It NEVER contacts UPI, banks, cards or wallets and NEVER transfers real money.

Donation remains Pending and enters protected funds only after Admin approval.

Run on laptop:
  pip install -r requirements.txt
  python app.py

Phone scanning on SAME Wi-Fi:
1. Connect laptop and phone to same Wi-Fi.
2. In Windows CMD run `ipconfig`. Find the laptop IPv4 address under active Wi-Fi.
3. Open the app on laptop using http://LAPTOP-IP:5000 (replace with actual IP).
   Create donation while using this address so QR encodes a phone-reachable URL.
4. Scan QR with phone camera. Allow Python through Windows Firewall on Private
   networks if prompted.

For phones on any network, deploy app to a public HTTPS host first.
The QR is a demo website URL, not a UPI payment QR.
