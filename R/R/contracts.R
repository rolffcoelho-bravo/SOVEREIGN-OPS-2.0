#' Sovereign Ops R Interface
#'
#' Cross-language wrappers for the Sovereign Ops decision envelope
#' and abstention protocol. Uses reticulate to call the Python contract
#' system for validated, reproducible reliability analysis.
#'
#' @name sovereignops-package
#' @docType package
NULL

#' Create a Decision Envelope
#'
#' Constructs a typed decision envelope through the Python contract system,
#' ensuring domain isolation and evidence validation.
#'
#' @param dataset_id Character. One of "ESA-AD-v2" or "EDP-SCADA-v2".
#' @param asset_id Character. Asset identifier within the domain.
#' @param outcome Character. One of "SUPPORTED_ALERT", "INVESTIGATE",
#'   "ABSTAIN_INSUFFICIENT_EVIDENCE", "BLOCK_DATA_INTEGRITY", "DEGRADED_SERVICE".
#' @param evidence List of model evidence objects (may be empty for non-actionable outcomes).
#' @param reasons Character vector of abstention reasons.
#'
#' @return A validated decision envelope (Python object via reticulate).
#'
#' @examples
#' \dontrun{
#' env <- decision_envelope(
#'   dataset_id = "EDP-SCADA-v2",
#'   asset_id = "turbine-T01",
#'   outcome = "ABSTAIN_INSUFFICIENT_EVIDENCE",
#'   evidence = list(),
#'   reasons = c("INSUFFICIENT_EVIDENCE", "STALE_DATA")
#' )
#' }
#'
#' @export
decision_envelope <- function(dataset_id, asset_id, outcome,
                               evidence = list(), reasons = character(0)) {
  contracts <- reticulate::import("sovereign_ops.contracts")
  reason_enums <- lapply(reasons, function(r) contracts$AbstentionReason(r))
  contracts$DecisionEnvelope(
    dataset_id = dataset_id,
    asset_id = asset_id,
    outcome = outcome,
    evidence = reticulate::tuple(evidence),
    reasons = reticulate::tuple(reason_enums)
  )
}

#' List Abstention Reasons
#'
#' Returns the five-value abstention vocabulary as a named character vector.
#'
#' @return Named character vector of abstention reason codes.
#'
#' @export
abstention_reasons <- function() {
  c(
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE",
    UNKNOWN_REGIME = "UNKNOWN_REGIME",
    STALE_DATA = "STALE_DATA",
    DATA_INTEGRITY = "DATA_INTEGRITY",
    COMPONENT_UNAVAILABLE = "COMPONENT_UNAVAILABLE"
  )
}

#' Read an Acquisition Manifest
#'
#' Reads and validates a JSON acquisition manifest (provenance receipt)
#' through the Python contract system.
#'
#' @param path Character. Path to the JSON manifest file.
#'
#' @return A validated AcquisitionManifest object.
#'
#' @export
read_manifest <- function(path) {
  contracts <- reticulate::import("sovereign_ops.contracts")
  raw <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  contracts$AcquisitionManifest(**raw)
}

#' Validate a Contract from JSON
#'
#' Parses a JSON string or file and validates it against a named contract type.
#'
#' @param json Character. JSON string or file path.
#' @param contract_type Character. Name of the contract class (e.g., "DecisionEnvelope").
#'
#' @return A validated contract object, or raises an error on validation failure.
#'
#' @export
validate_contract <- function(json, contract_type) {
  contracts <- reticulate::import("sovereign_ops.contracts")
  cls <- contracts[[contract_type]]
  if (file.exists(json)) {
    json <- readLines(json, warn = FALSE) |> paste(collapse = "\n")
  }
  cls$model_validate_json(json)
}
