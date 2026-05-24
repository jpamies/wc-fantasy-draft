# Notifications

This document describes browser notifications currently implemented in WC Fantasy and expected behavior.

## Current Scope

Notifications use the standard Browser Notification API.

Requirements:
- User enables notifications with the global nav button `🔔`.
- Browser permission is `granted`.
- The user session is logged in and has a valid team.

Important limitation:
- Matchday player events still use frontend polling every 45s.
- Web Push delivery requires VAPID keys configured on backend.

## Implemented Events

### Draft

Source:
- Draft WebSocket events in frontend draft page.
- Backend Web Push hook on draft turn changes.

Events:
- Your turn in draft.
- New pick in draft.

### Web Push Transport

Implemented:
- Service Worker at `/sw.js`.
- Browser push subscription lifecycle (subscribe/unsubscribe) from the global `🔔` button.
- Backend subscription storage and test push endpoint.

Current usage:
- Push test is sent when enabling notifications.
- Real background push for draft turn events is active.

### Matchday Player Events (New)

Source:
- Global frontend polling of:
  - `/api/v1/scoring/matchdays`
  - `/api/v1/teams/{team_id}/lineup-5/{matchday_id}`

Events:
- Active matchday started.
- Active matchday completed.
- Incomplete lineup warning (less than 5 starters in active matchday).
- A starter from your lineup moves to `country_played=true` (match started for that country).
- A starter increases `matchday_points` (points gained), with delta and new total.
- A starter decreases `matchday_points` (points adjustment), with delta and new total.

## Polling Strategy

- Interval: 45 seconds.
- Baseline: first poll per active matchday stores player state and does not send retroactive notifications.
- Dedupe key: per player, per matchday, based on previous stored state.

## Data Model Used

From `lineup-5` response (starters):
- `player_id`
- `name`
- `country_played`
- `matchday_points`

## Notes

- If there is no active matchday, no player-match notifications are sent.
- If browser notifications are disabled/blocked, no notifications are sent.
- Reopening the app during an already active matchday creates a fresh baseline for that browser session state.
- Lineup incomplete warning is emitted once per team + matchday in local browser storage.

## Backend Setup (Web Push)

Required environment variables:
- `WCF_PUSH_VAPID_PUBLIC_KEY`
- `WCF_PUSH_VAPID_PRIVATE_KEY`
- `WCF_PUSH_VAPID_SUBJECT` (example: `mailto:admin@fantasy.jpamies.com`)

When these are missing:
- App keeps working with in-tab notifications.
- Push subscription endpoints return disabled state.

Suggested key generation:
- Generate VAPID keys once and store them in Kubernetes secrets/env vars.

API endpoints:
- `GET /api/v1/notifications/push/public-key`
- `POST /api/v1/notifications/push/subscribe`
- `POST /api/v1/notifications/push/unsubscribe`
- `POST /api/v1/notifications/push/test`

## Future Improvements

- Hook Web Push sending into draft/market/scoring backend events (true background delivery for all categories).
- Notification preferences by category (draft, points, market, lineup lock).
- Backend event stream (single source of truth) to reduce polling.
