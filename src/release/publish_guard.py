"""Registry publish ref protection guard."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishRefContext:
    ref: str
    ref_name: str
    ref_type: str
    ref_protected: bool
    tag_signature_verified: bool = False


@dataclass(frozen=True)
class PublishRefDecision:
    allowed: bool
    reason: str
    ref: str
    ref_type: str


def validate_publish_ref(context: PublishRefContext) -> PublishRefDecision:
    if context.ref_type == "branch":
        if context.ref_protected:
            return PublishRefDecision(
                True,
                "protected_branch",
                context.ref,
                context.ref_type,
            )
        return PublishRefDecision(
            False,
            "unprotected_branch",
            context.ref,
            context.ref_type,
        )

    if context.ref_type == "tag":
        if not context.ref_name.startswith("v"):
            return PublishRefDecision(
                False,
                "tag_not_release_tag",
                context.ref,
                context.ref_type,
            )
        if context.tag_signature_verified:
            return PublishRefDecision(
                True,
                "signed_release_tag",
                context.ref,
                context.ref_type,
            )
        return PublishRefDecision(
            False,
            "unsigned_release_tag",
            context.ref,
            context.ref_type,
        )

    return PublishRefDecision(
        False,
        "unsupported_ref_type",
        context.ref,
        context.ref_type,
    )


def context_from_env() -> PublishRefContext:
    ref = os.getenv("GITHUB_REF", "")
    ref_name = os.getenv("GITHUB_REF_NAME", "")
    ref_type = os.getenv("GITHUB_REF_TYPE", "")
    if not ref_type:
        if ref.startswith("refs/heads/"):
            ref_type = "branch"
            ref_name = ref.removeprefix("refs/heads/")
        elif ref.startswith("refs/tags/"):
            ref_type = "tag"
            ref_name = ref.removeprefix("refs/tags/")
    return PublishRefContext(
        ref=ref,
        ref_name=ref_name,
        ref_type=ref_type,
        ref_protected=os.getenv("GITHUB_REF_PROTECTED", "").lower() == "true",
        tag_signature_verified=(
            os.getenv("TAG_SIGNATURE_VERIFIED", "").lower() == "true"
        ),
    )


def main() -> int:
    decision = validate_publish_ref(context_from_env())
    if decision.allowed:
        print(f"publish ref accepted: {decision.reason}")
        return 0
    print(f"::error::publish ref rejected: {decision.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
