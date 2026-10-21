// Authorization policies for the support agent (SG-ADP-04). Default deny: anything not permitted here is refused.
// Behaviour path: changes ship only in the scheduled release (CI release gate).

// SG-D9: a ticket is visible to its author and to the tenant's support and admin roles.
permit (principal, action == Action::"read_ticket", resource)
when { resource.tenant_id == principal.tenant_id && resource.author == principal };

permit (principal in Role::"tenant_support", action == Action::"read_ticket", resource)
when { resource.tenant_id == principal.tenant_id };

permit (principal in Role::"tenant_admin", action == Action::"read_ticket", resource)
when { resource.tenant_id == principal.tenant_id };

// Account data: its owner, or the tenant's admins.
permit (principal, action in [Action::"read_account", Action::"update_contact"], resource)
when { resource.tenant_id == principal.tenant_id && resource.owner == principal };

permit (principal in Role::"tenant_admin", action in [Action::"read_account", Action::"update_contact"], resource)
when { resource.tenant_id == principal.tenant_id };

// Production changes: the tenant's cloud admins.
permit (principal in Role::"cloud_admin", action in Action::"production_change", resource)
when { resource.tenant_id == principal.tenant_id };

// SG-D10: no production change inside a blackout window; the caller raises it for human approval instead.
forbid (principal, action in Action::"production_change", resource)
when { context.in_blackout };

// Tenant boundary: nothing crosses tenants, whatever else permits it.
forbid (principal, action, resource)
when { resource has tenant_id && resource.tenant_id != principal.tenant_id };
