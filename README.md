# World Cup 2026 Prediction League

I built this for fun, to play with friends and colleagues during the World Cup.

It's a small prediction league for the 2026 FIFA World Cup. Players sign in with their name and a passcode I've shared with them. They predict the winner (or a draw) for each of the 72 group matches, and who they think advances at every knockout round — group standings (1st/2nd/3rd), R32, R16, Quarter-Finals, Semi-Finals, Finalists, and the Champion. Each later round is constrained to the teams you yourself picked to advance in the previous round, so you build your own bracket as you go. Everything stays editable until a single shared deadline; after that the whole thing locks and points are tallied as I enter results.

It's a Streamlit app with Google Sheets as the backend, so all players, predictions, and results live in tabs of one spreadsheet. To run it locally, drop your Google service account JSON at `.streamlit/service_account.json`, then `pip install -r requirements.txt` and `streamlit run app.py`.
