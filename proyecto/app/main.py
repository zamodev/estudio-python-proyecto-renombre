"""Punto de entrada de la aplicación."""

import argparse
import logging

from app.config_loader import load_config
from app.dispatch_registry import DispatchRegistry
from app.destination_watcher import DestinationWatcher
from app.processor import FileProcessor
from app.watcher import DirectoryWatcher
from app.watcher_manager import WatcherManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def build_watchers(config, dry_run: bool = False):
    """Crea un watcher por cada carpeta configurada."""

    watchers = []
    destination_watchers = []

    for profile in config.watchers:
        rule_profile = config.rule_profiles.get(profile.rules_profile) if profile.rules_profile else None

        registry = None
        if profile.report_path:
            registry = DispatchRegistry(
                destination_path=profile.destination_path,
                report_path=profile.report_path,
            )

        processor = FileProcessor(
            destination_path=profile.destination_path,
            strategies_config=profile.strategies,
            rule_profile=rule_profile,
            dry_run=dry_run,
            dispatch_registry=registry,
        )

        watchers.append(
            DirectoryWatcher(
                name=profile.name,
                watch_path=profile.watch_path,
                processor=processor,
                process_existing_on_startup=profile.process_existing_on_startup,
                recursive=profile.recursive,
                stable_wait_seconds=profile.stable_wait_seconds,
                stability_checks=profile.stability_checks,
            )
        )

        if registry is not None:
            destination_watchers.append(
                DestinationWatcher(
                    name=profile.name,
                    destination_path=profile.destination_path,
                    registry=registry,
                )
            )

    return watchers, destination_watchers


def main():
    """Carga la configuración, inicia todos los watchers y mantiene viva la app."""

    parser = argparse.ArgumentParser(
        description="File MVP — Renombrador documental automatizado",
    )
    parser.add_argument(
        "--config",
        default="config/config.json",
        help="Ruta al archivo de configuración principal (default: config/config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula el procesamiento sin mover ni renombrar archivos.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging. Sobreescribe el valor definido en config.json.",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    effective_level = args.log_level or config.log_level
    logging.getLogger().setLevel(effective_level)

    if args.dry_run:
        logging.getLogger(__name__).warning(
            "Modo DRY-RUN activo: no se moverán ni renombrarán archivos reales."
        )

    watchers, destination_watchers = build_watchers(config, dry_run=args.dry_run)

    for dw in destination_watchers:
        dw.start()

    manager = WatcherManager(watchers)
    try:
        manager.run_forever()
    finally:
        for dw in destination_watchers:
            dw.stop()


if __name__ == "__main__":
    main()
