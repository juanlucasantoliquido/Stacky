import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Executions, Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
const PRECEDING = {
    business: null,
    functional: null,
    technical: "functional",
    developer: "technical",
    qa: "developer",
    custom: null,
};
export function useAutoFillBlocks() {
    const { activeTicketId, activeAgentType, setBlocks } = useWorkbench();
    const ticketQ = useQuery({
        queryKey: ["ticket", activeTicketId],
        queryFn: () => Tickets.byId(activeTicketId),
        enabled: activeTicketId != null,
    });
    const precedingType = activeAgentType ? PRECEDING[activeAgentType] : null;
    const precedingQ = useQuery({
        queryKey: ["last-approved", activeTicketId, precedingType],
        queryFn: () => Executions.list({
            ticket_id: activeTicketId,
            agent_type: precedingType,
            status: "completed",
        }),
        enabled: activeTicketId != null && precedingType != null,
    });
    // FA-09 — glossary auto-injection
    const glossaryQ = useQuery({
        queryKey: ["glossary", activeTicketId],
        queryFn: () => Tickets.glossary(activeTicketId),
        enabled: activeTicketId != null,
        staleTime: 5 * 60_000,
    });
    useEffect(() => {
        if (!activeTicketId || !activeAgentType) {
            setBlocks([]);
            return;
        }
        const ticket = ticketQ.data;
        const blocks = [];
        if (ticket) {
            blocks.push({
                id: "ticket-meta",
                kind: "auto",
                title: "Ticket metadata",
                content: [
                    `Title: ${ticket.title}`,
                    `ADO ID: ${ticket.ado_id}`,
                    `State: ${ticket.ado_state ?? ""}`,
                    `Priority: ${ticket.priority ?? ""}`,
                    ticket.description ? `\nDescription:\n${ticket.description}` : "",
                ]
                    .filter(Boolean)
                    .join("\n"),
                source: { type: "ticket", ticket_id: ticket.id },
            });
        }
        if (glossaryQ.data) {
            blocks.push(glossaryQ.data);
        }
        const lastApproved = precedingQ.data?.find((e) => e.verdict === "approved")
            ?? precedingQ.data?.[0];
        if (lastApproved) {
            blocks.push({
                id: `chain-from-${precedingType}`,
                kind: "auto",
                title: `Output del ${precedingType} (#${lastApproved.id})`,
                content: lastApproved.output ?? "(sin output)",
                source: { type: "execution", execution_id: lastApproved.id },
            });
        }
        blocks.push({
            id: "user-notes",
            kind: "editable",
            title: "Notas adicionales",
            content: "",
            source: { type: "user-input" },
        });
        setBlocks(blocks);
    }, [activeTicketId, activeAgentType, ticketQ.data, precedingQ.data, glossaryQ.data]);
}
