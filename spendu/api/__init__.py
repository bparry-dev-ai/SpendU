"""All the /api/... endpoints, one file per feature."""


def register_blueprints(app):
    from . import analytics, bills, budgets, dashboard, imports, lookups, recurring, spending

    for module in (lookups, spending, bills, budgets, recurring, dashboard, analytics, imports):
        app.register_blueprint(module.bp)
