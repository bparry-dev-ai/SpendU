"""All the /api/... endpoints, one file per feature."""


def register_blueprints(app):
    from . import analytics, bills, dashboard, imports, lookups, planner, recurring, spending

    for module in (lookups, spending, bills, planner, recurring, dashboard, analytics, imports):
        app.register_blueprint(module.bp)
