"""Lambda handler for tier evaluation scheduled events."""

from typing import Any, Dict
from datetime import datetime
from common.logger import (
    with_structured_logging,
    log_event_processing,
    log_dynamodb_operation,
    create_xray_subsegment,
    StructuredLogger
)


@with_structured_logging('tier-evaluation')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle scheduled tier evaluation events.

    This handler runs daily at 00:00 UTC to evaluate member tier promotions and demotions.
    It processes all members whose next evaluation date has passed and:
    - Calculates annual star count from transactions in past 12 months
    - Determines new tier based on thresholds (500 → Gold, 2500 → Reserve)
    - Handles demotion for members below thresholds after 12 months
    - Updates member tier, tier timestamp, and next evaluation date
    - Removes expiration dates from star ledger when promoting from Green
    - Records tier change transaction

    Args:
        event: EventBridge scheduled event
        context: Lambda context object
        logger: Structured logger instance

    Returns:
        Response dictionary with evaluation results
    """
    import json
    from datetime import datetime, timedelta
    from typing import List

    from common.dynamodb import DynamoDBClient
    from common.models import Tier, Transaction, TransactionType

    try:
        db_client = DynamoDBClient()
        current_time = datetime.utcnow()

        # Track evaluation results
        evaluations_processed = 0
        promotions = 0
        demotions = 0
        no_changes = 0
        errors = []

        logger.info("Starting scheduled tier evaluation", 
                   evaluation_time=current_time.isoformat(),
                   event_source=event.get('source', 'unknown'))

        # Query all members whose evaluation date has passed
        # We need to check all tiers since any member could be due for evaluation
        for tier in [Tier.GREEN, Tier.GOLD, Tier.RESERVE]:
            with create_xray_subsegment(f'evaluate_{tier.value.lower()}_members'):
                try:
                    start_time = datetime.utcnow()
                    members = db_client.query_members_by_tier(
                        tier=tier,
                        evaluation_date_before=current_time,
                        limit=1000  # Process in batches
                    )
                    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    log_dynamodb_operation(logger, 'query', 'rewards-program', 
                                         {'GSI1PK': f'TIER#{tier.value}'}, 
                                         success=True, duration_ms=duration_ms)

                    logger.info(f"Found members due for tier evaluation", 
                               tier=tier.value, member_count=len(members))

                    for member in members:
                        try:
                            evaluations_processed += 1

                            with create_xray_subsegment('calculate_annual_stars'):
                                # Calculate annual star count from transactions in past 12 months
                                annual_stars = _calculate_annual_stars(db_client, member.membership_id, current_time, logger)

                            # Determine new tier based on thresholds
                            new_tier = _determine_tier_from_stars(annual_stars)

                            logger.debug("Member tier evaluation calculated", 
                                        member_id=member.membership_id,
                                        annual_stars=annual_stars,
                                        current_tier=member.tier.value,
                                        new_tier=new_tier.value)

                            # Check if tier change is needed
                            if new_tier != member.tier:
                                with create_xray_subsegment('process_tier_change'):
                                    # Update member tier
                                    next_evaluation = current_time + timedelta(days=365)

                                    start_time = datetime.utcnow()
                                    db_client.update_member_tier(
                                        membership_id=member.membership_id,
                                        new_tier=new_tier,
                                        tier_since=current_time,
                                        next_evaluation=next_evaluation
                                    )
                                    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                                    log_dynamodb_operation(logger, 'update_item', 'rewards-program', 
                                                         {'PK': f'MEMBER#{member.membership_id}'}, 
                                                         success=True, duration_ms=duration_ms)

                                    # Update annual star count
                                    db_client.update_member(
                                        membership_id=member.membership_id,
                                        updates={'annualStarCount': annual_stars}
                                    )

                                    # If promoting from Green to Gold/Reserve, remove expiration dates
                                    if member.tier == Tier.GREEN and new_tier in [Tier.GOLD, Tier.RESERVE]:
                                        _remove_star_expiration_dates(db_client, member.membership_id, logger)

                                    # Record tier change transaction
                                    tier_change_transaction = Transaction(
                                        transaction_id=f"tier_eval_{member.membership_id}_{int(current_time.timestamp())}",
                                        membership_id=member.membership_id,
                                        type=TransactionType.TIER_CHANGE,
                                        timestamp=current_time,
                                        description=f"Tier changed from {member.tier.value} to {new_tier.value} "
                                                  f"based on {annual_stars} annual stars"
                                    )

                                    start_time = datetime.utcnow()
                                    db_client.record_transaction(tier_change_transaction)
                                    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                                    log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                                         {'PK': f'MEMBER#{member.membership_id}'}, 
                                                         success=True, duration_ms=duration_ms)

                                if new_tier.value > member.tier.value:  # Promotion
                                    promotions += 1
                                    logger.info("Member tier promotion", 
                                               member_id=member.membership_id,
                                               from_tier=member.tier.value,
                                               to_tier=new_tier.value,
                                               annual_stars=annual_stars)
                                else:  # Demotion
                                    demotions += 1
                                    logger.info("Member tier demotion", 
                                               member_id=member.membership_id,
                                               from_tier=member.tier.value,
                                               to_tier=new_tier.value,
                                               annual_stars=annual_stars)
                            else:
                                # No tier change, but update next evaluation date and annual star count
                                next_evaluation = current_time + timedelta(days=365)

                                db_client.update_member(
                                    membership_id=member.membership_id,
                                    updates={
                                        'nextTierEvaluation': next_evaluation,
                                        'annualStarCount': annual_stars
                                    }
                                )

                                # Update GSI1 keys for the new evaluation date
                                db_client.update_member_tier(
                                    membership_id=member.membership_id,
                                    new_tier=member.tier,  # Same tier
                                    tier_since=member.tier_since,  # Keep existing tier_since
                                    next_evaluation=next_evaluation
                                )

                                no_changes += 1
                                logger.debug("No tier change required", 
                                            member_id=member.membership_id,
                                            tier=member.tier.value,
                                            annual_stars=annual_stars,
                                            next_evaluation=next_evaluation.isoformat())

                        except Exception as e:
                            error_msg = f"Error evaluating member {member.membership_id}: {str(e)}"
                            logger.error("Member tier evaluation failed", 
                                        member_id=member.membership_id,
                                        exception_type=type(e).__name__,
                                        exception_message=str(e))
                            errors.append(error_msg)
                            continue

                except Exception as e:
                    error_msg = f"Error querying {tier.value} members: {str(e)}"
                    logger.error("Tier member query failed", 
                                tier=tier.value,
                                exception_type=type(e).__name__,
                                exception_message=str(e))
                    log_dynamodb_operation(logger, 'query', 'rewards-program', 
                                         {'GSI1PK': f'TIER#{tier.value}'}, 
                                         success=False, error=str(e))
                    errors.append(error_msg)
                    continue

        # Log summary
        logger.info("Tier evaluation completed", 
                   evaluations_processed=evaluations_processed,
                   promotions=promotions,
                   demotions=demotions,
                   no_changes=no_changes,
                   errors=len(errors))

        log_event_processing(logger, 'tier_evaluation', success=True,
                           evaluations_processed=evaluations_processed,
                           promotions=promotions, demotions=demotions,
                           no_changes=no_changes, errors=len(errors))

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Tier evaluation completed successfully',
                'results': {
                    'evaluations_processed': evaluations_processed,
                    'promotions': promotions,
                    'demotions': demotions,
                    'no_changes': no_changes,
                    'errors': len(errors)
                },
                'timestamp': current_time.isoformat()
            })
        }

    except Exception as e:
        logger.error("Fatal tier evaluation error", 
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        log_event_processing(logger, 'tier_evaluation', success=False, 
                           error="FATAL_ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error during tier evaluation',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }


def _calculate_annual_stars(db_client: 'DynamoDBClient', membership_id: str, current_time: datetime, logger: 'StructuredLogger') -> int:
    """
    Calculate annual star count from transactions in the past 12 months.
    
    Args:
        db_client: DynamoDB client instance
        membership_id: Member to calculate stars for
        current_time: Current timestamp for 12-month lookback
        logger: Structured logger instance
        
    Returns:
        Total stars earned in past 12 months
    """
    from datetime import timedelta
    from common.models import TransactionType
    
    # Calculate 12 months ago
    twelve_months_ago = current_time - timedelta(days=365)
    
    # Get all transactions for the member
    start_time = datetime.utcnow()
    transactions, _ = db_client.get_member_transactions(
        membership_id=membership_id,
        limit=1000  # Should be enough for most members
    )
    duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    log_dynamodb_operation(logger, 'query', 'rewards-program', 
                         {'PK': f'MEMBER#{membership_id}'}, 
                         success=True, duration_ms=duration_ms)
    
    annual_stars = 0
    for transaction in transactions:
        # Only count purchase transactions within the past 12 months
        if (transaction.type == TransactionType.PURCHASE and 
            transaction.timestamp >= twelve_months_ago and
            transaction.stars_earned is not None):
            annual_stars += transaction.stars_earned
    
    logger.debug("Annual stars calculated", 
                member_id=membership_id,
                annual_stars=annual_stars,
                transaction_count=len(transactions),
                lookback_date=twelve_months_ago.isoformat())
    
    return annual_stars


def _determine_tier_from_stars(annual_stars: int):
    """
    Determine tier based on annual star count.
    
    Thresholds:
    - 2500+ stars: Reserve
    - 500+ stars: Gold  
    - Below 500: Green
    
    Args:
        annual_stars: Total stars earned in past 12 months
        
    Returns:
        Appropriate tier based on star count
    """
    from common.models import Tier
    
    if annual_stars >= 2500:
        return Tier.RESERVE
    elif annual_stars >= 500:
        return Tier.GOLD
    else:
        return Tier.GREEN


def _remove_star_expiration_dates(db_client: 'DynamoDBClient', membership_id: str, logger: 'StructuredLogger') -> None:
    """
    Remove expiration dates from all star ledger entries when promoting from Green.
    
    When a member is promoted from Green to Gold or Reserve, their stars become
    non-expiring, so we need to remove the expiration dates from all existing
    star ledger entries.
    
    Args:
        db_client: DynamoDB client instance
        membership_id: Member whose star expiration dates to remove
        logger: Structured logger instance
    """
    try:
        # Get all star ledger entries for the member
        start_time = datetime.utcnow()
        star_entries = db_client.get_star_ledger_entries(membership_id)
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        log_dynamodb_operation(logger, 'query', 'rewards-program', 
                             {'PK': f'MEMBER#{membership_id}'}, 
                             success=True, duration_ms=duration_ms)
        
        if not star_entries:
            logger.debug("No star ledger entries found for expiration removal", 
                        member_id=membership_id)
            return
        
        # Update each entry to remove expiration date
        # Note: DynamoDB doesn't support batch updates, so we need to update individually
        updated_count = 0
        for entry in star_entries:
            try:
                # Update the star ledger entry to remove expiration date
                start_time = datetime.utcnow()
                db_client.table.update_item(
                    Key={
                        'PK': f'MEMBER#{membership_id}',
                        'SK': f'STAR#{entry.earned_date.isoformat()}#{entry.batch_id}'
                    },
                    UpdateExpression='REMOVE expirationDate'
                )
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                log_dynamodb_operation(logger, 'update_item', 'rewards-program', 
                                     {'PK': f'MEMBER#{membership_id}'}, 
                                     success=True, duration_ms=duration_ms)
                updated_count += 1
            except Exception as e:
                logger.error("Failed to remove expiration date from star entry", 
                            member_id=membership_id,
                            batch_id=entry.batch_id,
                            exception_message=str(e))
                # Continue with other entries even if one fails
                continue
        
        logger.info("Star expiration dates removed for promotion", 
                   member_id=membership_id,
                   total_entries=len(star_entries),
                   updated_entries=updated_count)
        
    except Exception as e:
        logger.error("Failed to remove star expiration dates", 
                    member_id=membership_id,
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        # Don't raise - this is not critical enough to fail the entire tier evaluation