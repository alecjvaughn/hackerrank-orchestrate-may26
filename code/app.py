import os
import sys
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich import box

# Ensure the current directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import main
import sync

console = Console()

class SupportApp:
    def __init__(self, mode="normal"):
        self.mode = mode # "test" (QAS) or "normal" (PRD)
        self.collection_name = "triage_queue_qas" if mode == "test" else "triage_queue_prd"
        self.db_fs, _ = main.get_db_clients()
        self.status_msg = "System Ready"
        
    def display_header(self):
        console.clear()
        mode_str = "[bold yellow]QAS / ADMIN[/bold yellow]" if self.mode == "test" else "[bold green]PRODUCTION[/bold green]"
        
        # Header Panel
        header = f"[bold blue]HackerRank Orchestrate Dashboard[/bold blue]\nMode: {mode_str} | Collection: {self.collection_name}"
        console.print(Panel(header, expand=True, border_style="blue"))
        
        # Status Area
        console.print(Panel(f"[bold cyan]STATUS:[/bold cyan] {self.status_msg}", border_style="cyan", padding=(0, 1)))

    def get_pending_tickets(self):
        """Fetches all tickets in PENDING state."""
        return list(self.db_fs.collection(self.collection_name).where("ticket_state", "==", "PENDING").stream())

    def update_status(self, msg):
        self.status_msg = msg
        self.display_header()

    def run(self):
        # QAS Wizard Choice
        if self.mode == "test":
            self.display_header()
            if Prompt.ask("Would you like to run the QAS Setup Wizard?", choices=["y", "n"], default="y") == "y":
                self.run_qas_wizard()
        
        while True:
            self.display_header()
            tickets = self.get_pending_tickets()
            
            if not tickets:
                self.update_status("[yellow]Nothing pending![/yellow]")
                sync_now = Prompt.ask("Sync from upstream now?", choices=["y", "n"], default="y")
                if sync_now == "y":
                    self.perform_sync()
                    continue
                else:
                    break
            
            # Show Queue Table
            table = Table(title="Pending Triage Queue", box=box.ROUNDED)
            table.add_column("ID", style="dim")
            table.add_column("Company", style="cyan")
            table.add_column("Subject", style="white")
            
            for doc in tickets[:5]:
                d = doc.to_dict()
                table.add_row(doc.id[:8] + "...", d.get("company"), d.get("subject"))
            
            console.print(table)
            if len(tickets) > 5:
                console.print(f"[dim]... and {len(tickets)-5} more.[/dim]")

            console.print("\n[bold cyan]Actions:[/bold cyan]")
            console.print("[1] Process Queue (Full Agent Mode)")
            console.print("[2] Manual Ticket Entry / Detail View")
            console.print("[3] Sync more from Upstream")
            console.print("[4] Generate Output CSV")
            console.print("[q] Quit")
            
            choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "q"], default="1")
            
            if choice == "1":
                self.process_queue_with_progress(tickets)
            elif choice == "2":
                self.detail_view_menu(tickets)
            elif choice == "3":
                self.perform_sync()
            elif choice == "4":
                self.update_status("Generating CSV...")
                main.generate_output(collection_name=self.collection_name, mode=self.mode)
                self.update_status("[bold green]Success:[/bold green] Output generated.")
                Prompt.ask("Press Enter to continue")
            elif choice == "q":
                break

    def perform_sync(self):
        if self.mode == "test":
            count = Prompt.ask("How many tickets to pull?", choices=["1", "5", "10"], default="1")
            self.update_status(f"Syncing {count} tickets...")
            sync.sync_tickets(mode="test", limit=int(count))
        else:
            self.update_status("Syncing all production tickets...")
            sync.sync_tickets(mode="normal")
        self.update_status("Sync complete.")

    def run_qas_wizard(self):
        """Guided sequence for Admin/QAS testing."""
        self.update_status("WIZARD: Step 1 - Re-initializing Queue")
        sync.reinitialize_queue(mode="test", count=sync.DEFAULT_REINIT_COUNT)
        
        self.update_status("WIZARD: Step 2 - Minimal Ingestion")
        from ingest import ingest_corpus
        ingest_corpus(mode="minimal")
        
        self.update_status("WIZARD: Step 3 - Processing Queue")
        tickets = self.get_pending_tickets()
        self.process_queue_with_progress(tickets)
        
        self.update_status("WIZARD: Setup Complete. Entering Main Dashboard.")
        Prompt.ask("Press Enter to continue")

    def process_queue_with_progress(self, tickets):
        total = len(tickets)
        if total == 0: return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Orchestrating agents...", total=total)
            
            def cb(tid, data, logger):
                progress.advance(task)
                console.print(f"  [green]✓[/green] Ticket {tid[:8]} triaged.")

            main.process_full_pipeline(
                collection_name=self.collection_name,
                eval_callback=cb
            )
        self.update_status("[bold green]Queue Processed.[/bold green]")
        Prompt.ask("\nProcessing complete. Press Enter to return to menu")

    def detail_view_menu(self, tickets):
        tid = Prompt.ask("Enter Ticket ID (or first 4 chars)")
        match = None
        for doc in tickets:
            if doc.id.startswith(tid):
                match = doc
                break
        
        if not match:
            self.update_status("[red]Error: Ticket not found.[/red]")
            Prompt.ask("Press Enter")
            return

        data = match.to_dict()
        while True:
            self.display_header()
            console.print(Panel(f"[bold]Ticket Details: {match.id}[/bold]", border_style="cyan"))
            
            # Non-longtext fields are easier to filter/view
            for k, v in data.items():
                if k in ["company", "product_area", "status", "request_type", "ticket_state"]:
                    console.print(f"[bold white]{k}:[/bold white] {v}")
            
            console.print("\n[bold cyan]Ticket Actions:[/bold cyan]")
            console.print("[1] Edit Field")
            console.print("[2] Archive (Hide)")
            console.print("[3] View Longtext (Issue/Response/Justification)")
            console.print("[b] Back to List")
            
            subchoice = Prompt.ask("Select", choices=["1", "2", "3", "b"], default="b")
            
            if subchoice == "1":
                field = Prompt.ask("Field to edit", choices=["product_area", "status", "request_type", "response", "justification"])
                new_val = Prompt.ask(f"New value for {field}")
                data[field] = new_val
                self.db_fs.collection(self.collection_name).document(match.id).update({field: new_val})
                self.update_status(f"Field {field} updated.")
            elif subchoice == "2":
                self.db_fs.collection(self.collection_name).document(match.id).update({"ticket_state": "ARCHIVED"})
                self.update_status("Ticket archived.")
                Prompt.ask("Press Enter")
                break
            elif subchoice == "3":
                console.clear()
                console.print(Panel(f"[bold white]ISSUE:[/bold white]\n{data.get('issue')}", border_style="white"))
                console.print(Panel(f"[bold white]RESPONSE:[/bold white]\n{data.get('response')}", border_style="white"))
                console.print(Panel(f"[bold white]JUSTIFICATION:[/bold white]\n{data.get('justification')}", border_style="white"))
                Prompt.ask("Press Enter to return to detail view")
            elif subchoice == "b":
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qas", action="store_true", help="Run in Admin / QAS mode")
    args = parser.parse_args()
    
    app = SupportApp(mode="test" if args.qas else "normal")
    app.run()
