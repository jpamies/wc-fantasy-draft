import sqlite3
c = sqlite3.connect('/data/wc_fantasy.db')
n = c.execute("UPDATE draft_settings SET autodraft=1 WHERE team_id IN (SELECT id FROM fantasy_teams WHERE owner_nick LIKE 'bot_%')").rowcount
c.commit()
print(f'Enabled autodraft for {n} bot rows')
