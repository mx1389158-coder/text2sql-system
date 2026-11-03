from scripts.audit_dataset_governance import normalized_question


def test_question_normalization_detects_punctuation_only_variants():
    assert normalized_question("近 3 个月，各型号报修率？") == normalized_question(
        "近3个月各型号报修率"
    )
