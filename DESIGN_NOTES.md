# Thermal Anomaly Detection – Design Notes

## 1. Design Choices

The application uses **FastAPI** because it provides a simple way to build
REST APIs, automatic request validation, and interactive Swagger
documentation.

**SQLite** was selected because it is lightweight, requires minimal setup, and
is sufficient for this assessment. **SQLAlchemy ORM** is used to interact
with the database through Python models.

The database contains four tables: Assets, Inspections, Alerts, and Alert
Acknowledgement History. Each inspection is uniquely identified by its asset
ID and timestamp. This prevents the same inspection from being stored more
than once.

Alert generation uses `max_temp_C` to determine whether an asset has crossed
its configured temperature limits. A critical alert is generated when the
maximum temperature reaches the critical limit. Otherwise, a warning alert is
generated when it reaches the warning limit.

Acknowledgement history is stored separately to maintain an audit trail
containing the operator, acknowledgement time, and previous and new status.
Database transactions help ensure that related changes are saved
consistently.

## 2. Future Improvements

- Add a web dashboard for monitoring assets and alerts.
- Introduce authentication and role-based access.
- Integrate real thermal camera data.
- Add email or mobile notifications for critical alerts.
- Migrate to PostgreSQL for larger deployments.
- Explore machine-learning-based anomaly detection.

## 3. Current Limitations

The current application is a backend API. It does not include a frontend
dashboard, authentication, actual thermal image processing, or
machine-learning-based prediction. Alerts are generated using configured
temperature thresholds.

## 4. AI Tool Usage

ChatGPT and GitHub Copilot were used for development assistance, including
planning, implementation guidance, code-generation assistance, debugging,
testing, and documentation. The application was run and tested during
development, and its functionality was verified against the assessment
requirements.
