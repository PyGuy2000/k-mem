"""Deterministic resolution.

mandatory  = records governing the target whose governing row came from
             the map (the read gate's set, nothing more)
advisory   = other records governing the target (contracts, fact docs), plus
             every record ONE explicit edge away from a mandatory record, in
             either direction, labelled with that edge
collisions = a mandatory ADR whose status is superseded, an incoming
             ``supersedes`` edge onto a mandatory ADR, or a PARKED plan
             reached from one

No score or similarity enters this function. The receipt hashes the request,
the mandatory ids and both revisions.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

from .models import AdvisoryRecord, ContextPacket, ContextRecord, ResolutionRequest
from .store import SQLiteStore


class ContextResolver:
    def __init__(self, store: SQLiteStore, matcher: Callable[[str], re.Pattern[str]]):
        self.store = store
        self.matcher = matcher

    def resolve(self, request: ResolutionRequest) -> ContextPacket:
        repo = request.repo or self.store.get_meta("repo")
        target = request.target.replace("\\", "/").lstrip("./")

        mandatory: dict[str, ContextRecord] = {}
        advisory: dict[tuple[str, str], AdvisoryRecord] = {}
        collisions: dict[tuple[str, str], AdvisoryRecord] = {}

        for rec, prov in self.store.governed_for_target(target, repo, self.matcher):
            if rec.record_type == "adr" and prov.get("mandatory"):
                mandatory[rec.record_id] = rec
            else:
                key = (str(prov.get("relation", "governs_path")), rec.record_id)
                advisory.setdefault(key, AdvisoryRecord(key[0], rec, prov))

        for m in sorted(mandatory.values(), key=lambda r: r.record_id):
            if m.status == "superseded":
                collisions.setdefault(("superseded", m.record_id), AdvisoryRecord("superseded", m, m.provenance))
            for relation, rec, prov in self.store.related_from(m.record_id):
                key = (relation, rec.record_id)
                if rec.record_id in mandatory:
                    continue
                advisory.setdefault(key, AdvisoryRecord(relation, rec, prov))
            for relation, rec, prov in self.store.related_to(m.record_id):
                if rec.record_id in mandatory:
                    continue
                if relation == "supersedes":
                    collisions.setdefault(("superseded_by", rec.record_id), AdvisoryRecord("superseded_by", rec, prov))
                    continue
                key = (f"{relation}:incoming", rec.record_id)
                advisory.setdefault(key, AdvisoryRecord(key[0], rec, prov))
                if rec.record_type == "plan" and rec.status == "parked":
                    collisions.setdefault(("parked_plan", rec.record_id), AdvisoryRecord("parked_plan", rec, prov))

        mand_list = [mandatory[k] for k in sorted(mandatory)]
        adv_list = [advisory[k] for k in sorted(advisory)]
        col_list = [collisions[k] for k in sorted(collisions)]

        source_revision = self.store.get_meta("source_revision")
        index_revision = self.store.get_meta("index_revision")
        payload = {
            "operation": request.operation,
            "target": target,
            "repo": repo,
            "mandatory": [r.record_id for r in mand_list],
            "source_revision": source_revision,
            "index_revision": index_revision,
        }
        receipt = "CTX-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

        return ContextPacket(
            request=ResolutionRequest(request.operation, target, repo),
            mandatory=mand_list,
            advisory=adv_list,
            collisions=col_list,
            receipt_id=receipt,
            source_revision=source_revision,
            index_revision=index_revision,
        )
