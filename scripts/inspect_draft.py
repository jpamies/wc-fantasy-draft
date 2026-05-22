import sqlite3, sys
c = sqlite3.connect('/data/wc_fantasy.db')
c.row_factory = sqlite3.Row
print('--- drafts ---')
for r in c.execute('SELECT id,league_id,status,current_round,current_pick FROM drafts'):
    print(dict(r))
print('--- draft_settings ---')
for r in c.execute('SELECT * FROM draft_settings'):
    print(dict(r))
print('--- bots ---')
for r in c.execute("SELECT id,team_name,owner_nick FROM fantasy_teams WHERE owner_nick LIKE 'bot_%'"):
    print(dict(r))
print('--- pick_order ---')
for r in c.execute("SELECT pick_order FROM drafts WHERE status='in_progress'"):
    print(r['pick_order'])
