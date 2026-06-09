"""Hyper-V host monitor via WinRM (pywinrm).

Connects to a Windows Server running Hyper-V, runs PowerShell remotely via
WinRM/NTLM, and returns VM status + host resource summary.

Required env keys: HYPERV_HOST, HYPERV_USERNAME, HYPERV_PASSWORD
"""
import json

TIMEOUT = 20


def collect(E, card_cfg=None):
    host = E.get("HYPERV_HOST", "").strip()
    user = E.get("HYPERV_USERNAME", "").strip()
    pwd  = E.get("HYPERV_PASSWORD", "").strip()

    base = {"vms": [], "vm_count": 0, "running": 0, "stopped": 0,
            "host_cpus": "?", "host_mem_gb": "?"}

    if not host or not user or not pwd or pwd.startswith("<"):
        return {**base, "state": "degraded", "note": "Hyper-V creds not configured"}

    try:
        import winrm
    except ImportError:
        return {**base, "state": "error", "note": "pywinrm not installed (pip install pywinrm)"}

    try:
        sess = winrm.Session(
            host,
            auth=(user, pwd),
            transport="ntlm",
            server_cert_validation="ignore",
            operation_timeout_sec=TIMEOUT,
            read_timeout_sec=TIMEOUT + 5,
        )

        # ── VM list ────────────────────────────────────────────────────────────
        ps_vms = (
            "try { "
            "  $vms = Get-VM | Select-Object Name, State, CPUUsage, "
            "    @{N='MemAssignedGB';E={[math]::Round($_.MemoryAssigned/1GB,2)}}, "
            "    @{N='MemDemandGB';E={[math]::Round($_.MemoryDemand/1GB,2)}}, "
            "    @{N='UptimeHours';E={[math]::Round($_.Uptime.TotalHours,1)}}; "
            "  if ($vms -eq $null) { Write-Output '[]' } "
            "  else { ConvertTo-Json -InputObject @($vms) -Depth 3 } "
            "} catch { Write-Output '[]' }"
        )
        r_vms = sess.run_ps(ps_vms)
        if r_vms.status_code != 0:
            err = (r_vms.std_err or b"").decode("utf-8", "replace")[:200].strip()
            return {**base, "state": "error", "note": f"PS error: {err or 'unknown'}"}

        raw = (r_vms.std_out or b"").decode("utf-8", "replace").strip()
        try:
            vms_raw = json.loads(raw) if raw else []
        except Exception:
            vms_raw = []
        if isinstance(vms_raw, dict):
            vms_raw = [vms_raw]

        # ── Host resources ─────────────────────────────────────────────────────
        ps_host = (
            "try { "
            "  $h = Get-VMHost | Select-Object LogicalProcessorCount, "
            "    @{N='MemCapGB';E={[math]::Round($_.MemoryCapacity/1GB,1)}}; "
            "  ConvertTo-Json -InputObject $h "
            "} catch { Write-Output '{}' }"
        )
        r_host = sess.run_ps(ps_host)
        host_raw = (r_host.std_out or b"").decode("utf-8", "replace").strip()
        try:
            host_info = json.loads(host_raw) if host_raw else {}
        except Exception:
            host_info = {}
        if isinstance(host_info, list):
            host_info = host_info[0] if host_info else {}

        # ── Parse VMs ─────────────────────────────────────────────────────────
        vms = []
        running = 0
        stopped = 0
        for vm in vms_raw:
            if not isinstance(vm, dict):
                continue
            state_raw = str(vm.get("State", "")).strip()
            # Hyper-V State enum: 2=Running, 3=Off, 6=Saved, 9=Paused, 10=Starting
            # PowerShell may return name ("Running") or integer string ("2")
            if state_raw in ("2", "Running"):
                vm_state = "Running"
                running += 1
            elif state_raw in ("3", "Off"):
                vm_state = "Off"
                stopped += 1
            elif state_raw in ("9", "Paused"):
                vm_state = "Paused"
                stopped += 1
            elif state_raw in ("6", "Saved"):
                vm_state = "Saved"
                stopped += 1
            else:
                vm_state = state_raw or "Unknown"
                stopped += 1
            vms.append({
                "name": str(vm.get("Name", "?")),
                "state": vm_state,
                "cpu": float(vm.get("CPUUsage", 0) or 0),
                "mem_assigned": float(vm.get("MemAssignedGB", 0) or 0),
                "mem_demand": float(vm.get("MemDemandGB", 0) or 0),
                "uptime_h": float(vm.get("UptimeHours", 0) or 0),
            })

        vm_count = len(vms)
        overall = "error" if vm_count == 0 and not host_info else (
            "warn" if stopped > 0 else "ok"
        )

        return {
            "state": overall,
            "vm_count": vm_count,
            "running": running,
            "stopped": stopped,
            "vms": vms,
            "host_cpus": host_info.get("LogicalProcessorCount", "?"),
            "host_mem_gb": host_info.get("MemCapGB", "?"),
            "host": host,
        }

    except Exception as e:
        return {**base, "state": "error", "note": f"{type(e).__name__}: {str(e)[:180]}"}
