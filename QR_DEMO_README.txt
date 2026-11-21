NGO Donation Tracker - QR Demo update

This ZIP is based on the exact uploaded NGO_Donation_Tracker_auth_pages project.
Existing pages, authentication flow, donation approval, protected funds, expenses,
transaction history and current theme are retained.

QR behavior:
- Each submitted donation request gets a unique QR reference.
- QR image is saved under static/uploads/donation_qr/.
- Donation remains Pending and is not counted in protected funds until Admin approves it.
- The QR is DEMO ONLY. It is not a UPI QR and does not accept or verify payments.
- Real payments require an NGO UPI/payment gateway and secure server-side payment verification.

Install and run from the folder containing app.py:
  pip install -r requirements.txt
  python app.py

Open the local URL printed by Flask (normally http://127.0.0.1:5000/).
