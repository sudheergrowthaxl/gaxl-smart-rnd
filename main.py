"""
DQ Shape Rules Derivation System - Main Entry Point

This script runs the LangGraph workflow to derive Data Quality Shape Rules
from the Contactors product dataset using OpenAI GPT-4o.

Usage:
    python main.py

Requirements:
    - Set OPENAI_API_KEY in .env file
    - Ensure profiling JSON exists at data/python_profiling 3.json
    - Ensure raw data exists at data/a7e6e2fc-6699-495a-9669-ec91804103f4_out 1 (1).xlsx

Output:
    - output/dq_rules.json: Rules in JSON format
    - output/dq_rules.xlsx: Rules in Excel format with multiple sheets
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.workflow.graph_builder import build_dq_workflow, get_workflow_diagram
from src.models.agent_state import create_initial_state
from src.config.settings import get_settings


def print_banner():
    """Print application banner."""
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║         DQ SHAPE RULES DERIVATION SYSTEM                         ║
║         ─────────────────────────────────────                     ║
║                                                                   ║
║         LangGraph + LangChain + OpenAI GPT-4o                    ║
║         Customer Ontology Project                                 ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)


def validate_environment():
    """Validate required files and settings exist."""
    settings = get_settings()

    print("Validating environment...")

    # Check API key
    if not settings.openai_api_key:
        print("  ✗ OPENAI_API_KEY not set in .env file")
        return False
    print("  ✓ OpenAI API key configured")

    # Check profiling file
    profiling_path = settings.profiling_abs_path
    if not profiling_path.exists():
        print(f"  ✗ Profiling file not found: {profiling_path}")
        return False
    print(f"  ✓ Profiling file exists: {profiling_path.name}")

    # Check raw data file (optional but recommended)
    raw_data_path = settings.raw_data_abs_path
    if raw_data_path.exists():
        print(f"  ✓ Raw data file exists: {raw_data_path.name}")
    else:
        print(f"  ⚠ Raw data file not found (validation will be skipped)")

    return True


async def run_workflow():
    """Run the DQ rule derivation workflow."""
    settings = get_settings()

    # Create initial state
    initial_state = create_initial_state(
        raw_data_path=str(settings.raw_data_abs_path),
        profiling_path=str(settings.profiling_abs_path),
        schema_path=str(settings.get_absolute_path(settings.schema_path)),
    )

    # Build workflow
    print("\nBuilding workflow...")
    workflow = build_dq_workflow(use_checkpointer=True)

    # Configure execution
    config = {
        "configurable": {
            "thread_id": f"dq_rule_derivation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        },
        "recursion_limit": 100, 
    }

    print("\n" + "="*70)
    print("STARTING WORKFLOW EXECUTION")
    print("="*70 + "\n")

    # Run workflow
    try:
        final_state = await workflow.ainvoke(initial_state, config)

        print("\n" + "="*70)
        print("WORKFLOW COMPLETE")
        print("="*70)

        # Print results
        print(f"\nOutput Files:")
        print(f"  JSON: {final_state.get('output_json_path', 'N/A')}")
        print(f"  Excel: {final_state.get('output_excel_path', 'N/A')}")

        # Print statistics
        validated_rules = final_state.get('validated_rules', [])
        print(f"\nStatistics:")
        print(f"  Total rules generated: {len(validated_rules)}")

        if validated_rules:
            # Count by category
            categories = {}
            severities = {}
            for rule in validated_rules:
                cat = rule.rule_category
                sev = rule.severity
                categories[cat] = categories.get(cat, 0) + 1
                severities[sev] = severities.get(sev, 0) + 1

            print(f"\n  Rules by Category:")
            for cat, count in sorted(categories.items()):
                print(f"    {cat}: {count}")

            print(f"\n  Rules by Severity:")
            for sev, count in sorted(severities.items(), key=lambda x: ['Critical', 'High', 'Medium', 'Low'].index(x[0]) if x[0] in ['Critical', 'High', 'Medium', 'Low'] else 99):
                print(f"    {sev}: {count}")

        # Print errors if any
        errors = final_state.get('errors', [])
        if errors:
            print(f"\n  Errors encountered: {len(errors)}")
            for error in errors[:5]:
                print(f"    - {error}")

        return final_state

    except Exception as e:
        print(f"\n✗ Workflow failed: {e}")
        raise


def main():
    """Main entry point."""
    print_banner()

    # Print workflow diagram
    print("Workflow Structure:")
    print(get_workflow_diagram())

    # Validate environment
    if not validate_environment():
        print("\n✗ Environment validation failed. Please fix the issues above.")
        sys.exit(1)

    print("\n" + "-"*70)

    # Run the async workflow
    try:
        asyncio.run(run_workflow())
        print("\n✓ DQ Rule Derivation completed successfully!")
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
