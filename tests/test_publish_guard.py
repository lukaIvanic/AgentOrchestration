from src.release.publish_guard import (
    PublishRefContext,
    validate_publish_ref,
)


def test_unprotected_branch_is_rejected_before_registry_auth():
    decision = validate_publish_ref(
        PublishRefContext(
            ref="refs/heads/feature/manual-release",
            ref_name="feature/manual-release",
            ref_type="branch",
            ref_protected=False,
        )
    )

    assert not decision.allowed
    assert decision.reason == "unprotected_branch"


def test_protected_release_branch_is_accepted():
    decision = validate_publish_ref(
        PublishRefContext(
            ref="refs/heads/release/2.4.2",
            ref_name="release/2.4.2",
            ref_type="branch",
            ref_protected=True,
        )
    )

    assert decision.allowed
    assert decision.reason == "protected_branch"


def test_signed_release_tag_is_accepted():
    decision = validate_publish_ref(
        PublishRefContext(
            ref="refs/tags/v2.4.2",
            ref_name="v2.4.2",
            ref_type="tag",
            ref_protected=False,
            tag_signature_verified=True,
        )
    )

    assert decision.allowed
    assert decision.reason == "signed_release_tag"


def test_unsigned_release_tag_is_rejected():
    decision = validate_publish_ref(
        PublishRefContext(
            ref="refs/tags/v2.4.2",
            ref_name="v2.4.2",
            ref_type="tag",
            ref_protected=False,
            tag_signature_verified=False,
        )
    )

    assert not decision.allowed
    assert decision.reason == "unsigned_release_tag"


def test_manual_dispatch_cannot_override_unprotected_ref():
    manual_dispatch_input = {"force_publish": "true"}
    decision = validate_publish_ref(
        PublishRefContext(
            ref="refs/heads/feature/force",
            ref_name="feature/force",
            ref_type="branch",
            ref_protected=False,
        )
    )

    assert manual_dispatch_input["force_publish"] == "true"
    assert not decision.allowed
    assert decision.reason == "unprotected_branch"
