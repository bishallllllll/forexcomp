"""
Aggressive Day-1 Competition Bot — Main Entry Point
Usage: python src/competition_main.py --target 30 --days 7 --llm azure
"""

import argparse
import logging
import os
from config import aggressive_config as cfg
from src.competition_coordinator import CompetitionCoordinator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(f"{cfg.LOG_DIR}/competition.log"),
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Aggressive Day-1 Forex Competition Bot")
    parser.add_argument("--target", type=float, default=30, help="Target return %% (default: 30)")
    parser.add_argument("--days", type=int, default=7, help="Competition duration days (default: 7)")
    parser.add_argument("--llm", choices=["azure", "bedrock"], default="azure", help="LLM backend (default: azure)")
    parser.add_argument("--cycles", type=int, default=None, help="Max cycles (for testing)")
    args = parser.parse_args()
    
    # Set LLM provider
    os.environ["LLM_PROVIDER"] = args.llm
    
    # Validate credentials
    if args.llm == "azure":
        if not os.environ.get("AZURE_OPENAI_KEY"):
            logger.error("AZURE_OPENAI_KEY environment variable not set")
            return 1
    elif args.llm == "bedrock":
        if not os.environ.get("AWS_PROFILE"):
            logger.error("AWS_PROFILE environment variable not set")
            return 1
    
    logger.info(f"Launching competition: target={args.target}%, days={args.days}, llm={args.llm}")
    
    try:
        coordinator = CompetitionCoordinator(
            target_return=args.target,
            days=args.days,
            llm_provider=args.llm
        )
        coordinator.run(max_cycles=args.cycles)
        return 0
    except Exception as e:
        logger.error(f"Competition failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    exit(main())
