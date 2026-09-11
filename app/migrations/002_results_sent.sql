-- Which week's results text has gone out, so it's sent exactly once per
-- syndicate/season/week (replaces matching on message text).
CREATE TABLE results_sent (
    syndicate_id VARCHAR NOT NULL,
    season       INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    sent_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (syndicate_id, season, week)
);

-- Weeks already fully graded when this ships are history: never text them.
INSERT INTO results_sent
SELECT p.syndicate_id, p.season, p.week, now()::TIMESTAMP
FROM picks p LEFT JOIN pick_results r ON r.pick_id = p.id
GROUP BY 1, 2, 3
HAVING COUNT(r.pick_id) = COUNT(*);
