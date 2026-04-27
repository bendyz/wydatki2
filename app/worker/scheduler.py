"""
Scheduler zadań w tle dla systemu abonamentów.
Uruchamia się raz dziennie o północy i generuje wydatki z subskrypcji.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.crud.subscription import get_due_subscriptions, process_subscription_billing
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Globalny scheduler (singleton)
_scheduler: BackgroundScheduler | None = None


def process_daily_subscriptions():
    """
    Główna funkcja schedulera – pobiera wszystkie 'należne' subskrypcje
    i generuje z nich wydatki. Wywoływana raz dziennie.
    """
    logger.info("🔄 Rozpoczynam przetwarzanie abonamentów...")

    db = SessionLocal()
    try:
        due_subscriptions = get_due_subscriptions(db)
        logger.info(
            f"Znaleziono {len(due_subscriptions)} abonamentów do przetworzenia."
        )

        created_count = 0
        skipped_count = 0

        for subscription in due_subscriptions:
            try:
                expense = process_subscription_billing(db, subscription)
                if expense:
                    logger.info(
                        f"✅ Utworzono wydatek ID={expense.id} "
                        f"z abonamentu '{subscription.name}' "
                        f"na kwotę {subscription.amount} zł"
                    )
                    created_count += 1
                else:
                    logger.warning(
                        f"⏭️ Pominięto abonament '{subscription.name}' – prawdopodobnie wygasł"
                    )
                    skipped_count += 1
            except Exception as e:
                logger.error(
                    f"❌ Błąd podczas przetwarzania abonamentu ID={subscription.id}: {e}",
                    exc_info=True,
                )
                # Rollback tylko dla tej transakcji, aby nie zatrzymać pozostałych
                db.rollback()

        logger.info(
            f"🏁 Zakończono przetwarzanie abonamentów: "
            f"utworzono {created_count}, pominięto {skipped_count}."
        )

    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """
    Tworzy i uruchamia scheduler w tle.
    Zadanie uruchamia się codziennie o 00:00 (północ).
    Dodatkowo uruchamia się jednorazowo przy starcie aplikacji,
    aby obsłużyć ewentualne zaległości (np. serwer był wyłączony).
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler już działa, pomijam ponowne uruchomienie.")
        return _scheduler

    _scheduler = BackgroundScheduler()

    # Główne zadanie – codziennie o północy
    _scheduler.add_job(
        process_daily_subscriptions,
        trigger=CronTrigger(hour=0, minute=0),
        id="daily_subscription_billing",
        name="Generowanie wydatków z abonamentów (codziennie o północy)",
        replace_existing=True,
    )

    # Jednorazowe zadanie przy starcie – obsługa zaległości
    _scheduler.add_job(
        process_daily_subscriptions,
        trigger="date",  # uruchomi się raz, natychmiast
        id="startup_subscription_billing",
        name="Generowanie wydatków z abonamentów (przy starcie)",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("⏰ Scheduler uruchomiony. Następne zadanie: codziennie o 00:00.")

    return _scheduler


def shutdown_scheduler():
    """Zatrzymuje scheduler przy wyłączaniu aplikacji."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("⏹️ Scheduler zatrzymany.")
        _scheduler = None
