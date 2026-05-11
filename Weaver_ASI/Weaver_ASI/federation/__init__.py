"""
Federation package — distributed institutional cognition for Weaver ASI.

Enables multiple Weaver instances to synchronise their epistemic graphs,
exchange trust scores, arbitrate cross-instance conflicts, and run
distributed council deliberations.

Modules:
    graph_sync             — Serialize + merge graphs between instances.
    intergraph_arbitration — Resolve conflicts when graphs disagree.
    trust_exchange         — Exchange agent trust scores between instances.
    distributed_consensus  — Council deliberation across instances.
"""
from __future__ import annotations

from Weaver_ASI.federation.graph_sync import GraphSync
from Weaver_ASI.federation.intergraph_arbitration import IntergraphArbitration
from Weaver_ASI.federation.trust_exchange import TrustExchange
from Weaver_ASI.federation.distributed_consensus import DistributedConsensus

__all__ = [
    "GraphSync",
    "IntergraphArbitration",
    "TrustExchange",
    "DistributedConsensus",
]
